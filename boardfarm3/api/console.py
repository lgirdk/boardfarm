"""Capture of boardfarm console and framework log output."""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import itertools
import logging
import shutil
import sys
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
    from pathlib import Path

CONSOLE_LOGGER = "pexpect"
FRAMEWORK_LOGGER = "boardfarm3"
# The session's complete console log, next to its other artifacts. Also its
# member name inside a diagnostics bundle.
CONSOLE_FULL_NAME = "console_full.txt.gz"
# The longest a line waits in the compressor before it reaches the file.
# Flushing every line (a sync flush and a write per console chunk, under the
# handler lock) slows the console path and spoils the compression.
_FLUSH_INTERVAL = 1.0


def console_download_name(session_id: str) -> str:
    """Return the file name a console download is served under.

    :param session_id: session identifier
    :type session_id: str
    :return: ``<session_id>-console_full.txt.gz``
    :rtype: str
    """
    return f"{session_id}-{CONSOLE_FULL_NAME}"


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
    """Logging handler feeding console and framework records into a buffer.

    With a ``log_dir`` it also appends every event's line, in arrival order,
    to ``console_full.txt.gz`` there, so the complete log survives the
    bounded buffer.
    """

    def __init__(
        self,
        buffer: EventBuffer,
        *,
        log_dir: Path | None = None,
    ) -> None:
        """Initialise the handler.

        :param buffer: buffer to append captured events to
        :type buffer: EventBuffer
        :param log_dir: directory for ``console_full.txt.gz``, None for none
        :type log_dir: Path | None
        """
        super().__init__(level=logging.DEBUG)
        self._buffer = buffer
        self._previous_propagate: dict[str, bool] = {}
        self._log_dir = log_dir
        self._file: gzip.GzipFile | None = None
        self._last_flush = 0.0
        # Flushes what the last lines left in the compressor, once they stop.
        self._flush_timer: threading.Timer | None = None

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
            self.record(
                stream=stream,
                device=device,
                job_id=current_job_id.get(),
                line=line,
            )
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            # A handler must never raise into the code that logged.
            self.handleError(record)

    def record(
        self,
        *,
        stream: str,
        device: str | None,
        job_id: str | None,
        line: str,
    ) -> ConsoleEvent:
        """Append an event to the buffer and to the full log file.

        Also the entry point for lines that never pass through ``logging``,
        such as a run mode's output.

        :param stream: ``"console"``, ``"framework"`` or a mode's stream name
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
        event = self._buffer.append(
            stream=stream, device=device, job_id=job_id, line=line
        )
        if self._log_dir is not None:
            with self.lock:
                self._append_to_file(line)
        return event

    def _append_to_file(self, line: str) -> None:
        """Append *line* to the gzipped full log; called with ``self.lock`` held.

        :param line: the log line
        :type line: str
        """
        log_dir = self._log_dir
        if log_dir is None:
            return
        try:
            if self._file is None:
                log_dir.mkdir(parents=True, exist_ok=True)
                # Append mode starts a new gzip member; concatenated members
                # are one valid stream to zcat and to gzip.open().
                self._file = gzip.open(log_dir / CONSOLE_FULL_NAME, "ab")  # noqa: SIM115
            self._file.write(f"{line}\n".encode("utf-8", "replace"))
            self._flush_soon()
        except OSError as exc:
            self._disable_file(exc)

    def _flush_soon(self) -> None:
        """Flush now, or within the flush interval; called with ``self.lock`` held."""
        wait = self._last_flush + _FLUSH_INTERVAL - time.monotonic()
        if wait <= 0:
            self._flush_file()
        elif self._flush_timer is None:
            self._flush_timer = threading.Timer(wait, self._timed_flush)
            self._flush_timer.daemon = True
            self._flush_timer.start()

    def _flush_file(self) -> None:
        """Flush the open log file; called with ``self.lock`` held."""
        if self._file is not None:
            # Z_SYNC_FLUSH: everything written so far can be decompressed,
            # even while the file is open or after the agent dies.
            self._file.flush()
            self._last_flush = time.monotonic()

    def _timed_flush(self) -> None:
        """Flush the lines written since the last flush (timer thread)."""
        with self.lock:
            self._flush_timer = None
            try:
                self._flush_file()
            except OSError as exc:
                self._disable_file(exc)

    def _disable_file(self, exc: OSError) -> None:
        """Stop writing the log file after *exc*; called with ``self.lock`` held.

        :param exc: the error writing the file
        :type exc: OSError
        """
        # Never through logging: that would recurse into this handler.
        sys.stderr.write(f"console log file disabled ({self._log_dir}): {exc}\n")
        self._log_dir = None
        self._close_handle()

    def _close_handle(self) -> None:
        """Close the log file if open; called with ``self.lock`` held."""
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.close()
            self._file = None

    def close_file(self) -> None:
        """Finalise the log file so readers see a complete gzip stream.

        A later line reopens it in append mode, as a new gzip member.
        """
        with self.lock:
            self._close_handle()

    def log_file(self) -> Path | None:
        """Return the full log file, if anything has been written to it.

        :return: ``<log_dir>/console_full.txt.gz``, or None
        :rtype: Path | None
        """
        if self._log_dir is None:
            return None
        path = self._log_dir / CONSOLE_FULL_NAME
        return path if path.is_file() else None

    def copy_log_file(self, dest: Path) -> bool:
        """Copy the full log, finalised, to *dest*.

        Done under the handler lock so no line can land half-way through the
        copy: the copy is a complete gzip stream of everything logged so far.

        :param dest: file to write
        :type dest: Path
        :return: False when there is no log file to copy
        :rtype: bool
        """
        with self.lock:
            self._close_handle()
            path = self.log_file()
            if path is None:
                return False
            shutil.copyfile(path, dest)
        return True

    def close(self) -> None:
        """Finalise the log file, then close the handler."""
        self.close_file()
        super().close()

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
        self.close()
