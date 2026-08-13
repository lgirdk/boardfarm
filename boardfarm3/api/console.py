"""Capture of boardfarm console and framework log output."""

from __future__ import annotations

import asyncio
import logging
import time
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


class EventBuffer:
    """Bounded, cursor-ordered store of console and framework events."""

    def __init__(self, maxlen: int = 50_000) -> None:
        """Initialise the buffer.

        :param maxlen: how many events to retain
        :type maxlen: int
        """
        self._events: deque[ConsoleEvent] = deque(maxlen=maxlen)
        self._next_seq = 0
        self._subscribers: list[asyncio.Queue[ConsoleEvent]] = []

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
        for queue in self._subscribers:
            queue.put_nowait(event)
        return event

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
        selected: list[ConsoleEvent] = []
        truncated = False
        for event in self._events:
            if event.seq < cursor:
                continue
            if device is not None and event.device != device:
                continue
            if stream is not None and event.stream != stream:
                continue
            if job_id is not None and event.job_id != job_id:
                continue
            selected.append(event)
            if len(selected) >= limit:
                truncated = True
                break
        # When the scan stops early because `limit` was hit, the next cursor
        # must resume right after the last event actually returned -- not
        # jump to the buffer's global append-tail, which would silently skip
        # every event in between on the caller's next read().
        next_cursor = selected[-1].seq + 1 if truncated else self._next_seq
        return selected, next_cursor

    @property
    def next_seq(self) -> int:
        """Sequence number the next appended event will carry.

        :return: next sequence number
        :rtype: int
        """
        return self._next_seq

    async def subscribe(self) -> AsyncIterator[ConsoleEvent]:
        """Yield events as they arrive, for SSE streaming.

        :yield: newly appended events
        :rtype: AsyncIterator[ConsoleEvent]
        """
        queue: asyncio.Queue[ConsoleEvent] = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.remove(queue)

    @asynccontextmanager
    async def subscription(self) -> AsyncIterator[asyncio.Queue[ConsoleEvent]]:
        """Register a live subscriber and yield its queue.

        Registers before yielding so the caller can drain historical events
        without missing any that arrive during the drain.

        :yield: queue that receives every event appended after this call
        :rtype: asyncio.Queue[ConsoleEvent]
        """
        queue: asyncio.Queue[ConsoleEvent] = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            yield queue
        finally:
            self._subscribers.remove(queue)


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
        if record.name == CONSOLE_LOGGER or record.name.startswith(
            f"{CONSOLE_LOGGER}.",
        ):
            stream = "console"
            parts = record.name.split(".")
            device = parts[1] if len(parts) > 2 else None  # noqa: PLR2004
        else:
            stream = "framework"
            device = None
        self._buffer.append(
            stream=stream,
            device=device,
            job_id=current_job_id.get(),
            line=record.getMessage(),
        )

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
