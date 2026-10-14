"""Capture of boardfarm console and framework log output."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import threading
import time
import traceback
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from boardfarm3.api.execution import current_job_id

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

CONSOLE_LOGGER = "pexpect"
FRAMEWORK_LOGGER = "boardfarm3"


@dataclass(frozen=True)
class ConsoleEvent:
    """One captured line of console or framework output."""

    seq: int
    ts: float
    stream: str
    device: str | None
    job_id: str | None
    line: str


def _put_dropping_oldest(
    queue: asyncio.Queue[ConsoleEvent],
    event: ConsoleEvent,
) -> None:
    """Queue *event*, dropping the oldest queued event when the queue is full.

    Runs on the subscriber's event loop. The reader sees the drop as a gap in
    ``seq``.

    :param queue: subscriber queue
    :type queue: asyncio.Queue[ConsoleEvent]
    :param event: event to deliver
    :type event: ConsoleEvent
    """
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(event)


def _matches(
    event: ConsoleEvent,
    device: str | None,
    stream: str | None,
    job_id: str | None,
) -> bool:
    return (
        (device is None or event.device == device)
        and (stream is None or event.stream == stream)
        and (job_id is None or event.job_id == job_id)
    )


class EventBuffer:
    """Bounded, cursor-ordered store of console and framework events.

    Written from the pexpect worker thread and read on the event loop, so all
    state is guarded by a lock and live subscribers are fed through their own
    loop with ``call_soon_threadsafe``.
    """

    def __init__(self, maxlen: int = 50_000, subscriber_limit: int = 10_000) -> None:
        """Initialise the buffer.

        :param maxlen: how many events to retain
        :type maxlen: int
        :param subscriber_limit: how many undelivered events one live
            subscriber may hold before the oldest are dropped
        :type subscriber_limit: int
        """
        self._events: deque[ConsoleEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._next_seq = 0
        self._subscriber_limit = subscriber_limit
        self._subscribers: list[
            tuple[asyncio.AbstractEventLoop, asyncio.Queue[ConsoleEvent]]
        ] = []
        self._last_event: ConsoleEvent | None = None
        self._last_event_ts: float = time.time()

    def append(
        self,
        *,
        stream: str,
        device: str | None,
        job_id: str | None,
        line: str,
    ) -> ConsoleEvent:
        """Append an event and notify subscribers.

        :param stream: ``"console"`` or ``"framework"``
        :type stream: str
        :param device: device the line came from, if any
        :type device: str | None
        :param job_id: job that was running when the line was produced
        :type job_id: str | None
        :param line: the log line
        :type line: str
        :return: the stored event
        :rtype: ConsoleEvent
        """
        with self._lock:
            event = ConsoleEvent(
                seq=self._next_seq,
                ts=time.time(),
                stream=stream,
                device=device,
                job_id=job_id,
                line=line,
            )
            self._next_seq += 1
            self._events.append(event)
            self._last_event = event
            self._last_event_ts = event.ts
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            self._deliver(loop, queue, event)
        return event

    @staticmethod
    def _deliver(
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[ConsoleEvent],
        event: ConsoleEvent,
    ) -> None:
        """Hand *event* to a subscriber on the subscriber's own loop.

        :param loop: loop the subscriber's queue belongs to
        :type loop: asyncio.AbstractEventLoop
        :param queue: subscriber queue
        :type queue: asyncio.Queue[ConsoleEvent]
        :param event: event to deliver
        :type event: ConsoleEvent
        """
        try:
            on_loop = asyncio.get_running_loop() is loop
        except RuntimeError:
            on_loop = False
        if on_loop:
            _put_dropping_oldest(queue, event)
            return
        # RuntimeError: the subscriber's loop has already closed.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(_put_dropping_oldest, queue, event)

    def read(
        self,
        cursor: int = 0,
        device: str | None = None,
        stream: str | None = None,
        job_id: str | None = None,
        limit: int = 1000,
    ) -> tuple[list[ConsoleEvent], int]:
        """Read events at or after a cursor, optionally filtered.

        :param cursor: first sequence number to return
        :type cursor: int
        :param device: only events from this device
        :type device: str | None
        :param stream: only events from this stream
        :type stream: str | None
        :param job_id: only events produced during this job
        :type job_id: str | None
        :param limit: maximum events to return
        :type limit: int
        :return: matching events and the next cursor
        :rtype: tuple[list[ConsoleEvent], int]
        """
        with self._lock:
            next_seq = self._next_seq
            if not self._events:
                return [], next_seq
            # seq is contiguous inside the deque, so the cursor maps to an
            # offset; copy only from there, under the lock, and filter outside.
            start = 0 if cursor < 0 else max(0, cursor - self._events[0].seq)
            snapshot = list(itertools.islice(self._events, start, None))
        if cursor < 0:
            # The last -cursor events *matching the filters*, like tail(1).
            tail = [e for e in snapshot if _matches(e, device, stream, job_id)]
            candidates = tail[-abs(cursor) :]
        else:
            candidates = [e for e in snapshot if _matches(e, device, stream, job_id)]
        selected = candidates[:limit]
        # When `limit` cuts the scan short, the next cursor must resume right
        # after the last event returned -- not jump to the append-tail, which
        # would silently skip every event in between on the next read().
        truncated = len(selected) >= limit
        next_cursor = selected[-1].seq + 1 if truncated else next_seq
        return selected, next_cursor

    @property
    def next_seq(self) -> int:
        """Sequence number the next appended event will carry.

        :return: next sequence number
        :rtype: int
        """
        return self._next_seq

    @property
    def last_event_ts(self) -> float:
        """Timestamp of the most recent event, or of buffer creation.

        :return: UNIX timestamp
        :rtype: float
        """
        return self._last_event_ts

    @property
    def last_line(self) -> str | None:
        """Text of the most recent event, or None when nothing was captured.

        :return: last captured line
        :rtype: str | None
        """
        return self._last_event.line if self._last_event is not None else None

    async def subscribe(self) -> AsyncIterator[ConsoleEvent]:
        """Yield events as they arrive, for SSE streaming.

        :yield: newly appended events
        :rtype: AsyncIterator[ConsoleEvent]
        """
        async with self.subscription() as queue:
            while True:
                yield await queue.get()

    @asynccontextmanager
    async def subscription(self) -> AsyncIterator[asyncio.Queue[ConsoleEvent]]:
        """Register a live subscriber and yield its queue.

        Registers before yielding so the caller can drain historical events
        without missing any that arrive during the drain.

        :yield: queue that receives every event appended after this call
        :rtype: asyncio.Queue[ConsoleEvent]
        """
        queue: asyncio.Queue[ConsoleEvent] = asyncio.Queue(
            maxsize=self._subscriber_limit,
        )
        entry = (asyncio.get_running_loop(), queue)
        with self._lock:
            self._subscribers.append(entry)
        try:
            yield queue
        finally:
            with self._lock:
                self._subscribers.remove(entry)


class ConsoleCapture(logging.Handler):
    """Logging handler feeding console and framework records into a buffer."""

    def __init__(self, buffer: EventBuffer) -> None:
        """Initialise the handler.

        :param buffer: buffer to append captured events to
        :type buffer: EventBuffer
        """
        super().__init__(level=logging.DEBUG)
        self._buffer = buffer
        self._previous_propagate: dict[str, bool] = {}

    def emit(self, record: logging.LogRecord) -> None:
        """Append a log record to the buffer.

        :param record: log record to capture
        :type record: logging.LogRecord
        """
        try:
            if record.name == CONSOLE_LOGGER or record.name.startswith(
                f"{CONSOLE_LOGGER}.",
            ):
                stream = "console"
                parts = record.name.split(".")
                device = parts[1] if len(parts) > 2 else None  # noqa: PLR2004
            else:
                stream = "framework"
                device = None
            line = record.getMessage()
            if record.exc_info:
                # getMessage() drops exc_info entirely, which is how every
                # traceback was being lost on the way into the buffer.
                formatted = "".join(traceback.format_exception(*record.exc_info))
                line = f"{line}\n{formatted}"
            self._buffer.append(
                stream=stream,
                device=device,
                job_id=current_job_id.get(),
                line=line,
            )
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            # A handler must never raise into the code that logged.
            self.handleError(record)

    def install(self) -> None:
        """Attach to the console and framework loggers.

        Console traffic stops propagating to the root logger so it never
        floods the agent's own stdout.

        Idempotent: calling this again before ``uninstall()`` neither
        re-snapshots an already-modified ``propagate`` value nor attaches a
        second copy of the handler.
        """
        for name in (CONSOLE_LOGGER, FRAMEWORK_LOGGER):
            logger = logging.getLogger(name)
            if name not in self._previous_propagate:
                self._previous_propagate[name] = logger.propagate
            if self not in logger.handlers:
                logger.addHandler(self)
            logger.setLevel(logging.DEBUG)
        logging.getLogger(CONSOLE_LOGGER).propagate = False

    def uninstall(self) -> None:
        """Detach from the loggers and restore propagation."""
        for name, propagate in self._previous_propagate.items():
            logger = logging.getLogger(name)
            logger.removeHandler(self)
            logger.propagate = propagate
        self._previous_propagate.clear()
