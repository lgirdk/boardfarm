"""Thread-safe fan-out of raw console chunks, and the terminal WebSocket pump."""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.websockets import WebSocket


# A close frame's reason may carry at most 123 bytes of UTF-8.
REASON_MAX_BYTES = 123


def bound_reason(reason: str, limit: int = REASON_MAX_BYTES) -> str:
    """Cut *reason* to *limit* UTF-8 bytes without splitting a character.

    :param reason: close reason
    :type reason: str
    :param limit: maximum encoded length in bytes
    :type limit: int
    :return: *reason*, or its longest prefix that fits
    :rtype: str
    """
    data = reason.encode()
    if len(data) <= limit:
        return reason
    # Cutting can only leave an incomplete sequence at the end; drop it.
    return data[:limit].decode("utf-8", "ignore")


def _put_dropping_oldest(queue: asyncio.Queue[str | None], item: str | None) -> None:
    """Queue *item*, dropping the oldest queued item when the queue is full.

    Runs on the subscriber's event loop.

    :param queue: subscriber queue
    :type queue: asyncio.Queue[str | None]
    :param item: chunk (or ``None`` sentinel) to deliver
    :type item: str | None
    """
    if queue.full():
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()
    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(item)


class Fanout:
    """Deliver raw console chunks to any number of asyncio queues.

    ``publish`` may be called from any thread (the pexpect reader); queues are
    fed on the loop given at construction.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, maxsize: int = 1000) -> None:
        """Initialise the fan-out.

        :param loop: event loop that owns the subscriber queues
        :type loop: asyncio.AbstractEventLoop
        :param maxsize: chunks a subscriber may hold before the oldest drop
        :type maxsize: int
        """
        self._loop = loop
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._queues: list[asyncio.Queue[str | None]] = []

    def subscribe(self) -> asyncio.Queue[str | None]:
        """Register a subscriber.

        :return: queue receiving every chunk published afterwards
        :rtype: asyncio.Queue[str | None]
        """
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self._maxsize)
        with self._lock:
            self._queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str | None]) -> None:
        """Remove a subscriber; unknown queues are ignored.

        :param queue: queue returned by :meth:`subscribe`
        :type queue: asyncio.Queue[str | None]
        """
        with self._lock, contextlib.suppress(ValueError):
            self._queues.remove(queue)

    def _deliver(self, item: str | None) -> None:
        with self._lock:
            queues = list(self._queues)
        for queue in queues:
            # RuntimeError: the loop has already closed.
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(_put_dropping_oldest, queue, item)

    def publish(self, chunk: str) -> None:
        """Deliver a chunk to every subscriber without blocking.

        :param chunk: raw console output
        :type chunk: str
        """
        self._deliver(chunk)

    def close(self) -> None:
        """Put the ``None`` sentinel on every subscriber queue."""
        self._deliver(None)


async def send_status(
    ws: WebSocket,
    role: str,
    owner: str | None,
    state: str,
    held_by: str | None = None,
) -> None:
    """Send a ``status`` control message on a terminal socket.

    :param ws: terminal WebSocket
    :type ws: WebSocket
    :param role: ``control`` or ``view``
    :type role: str
    :param owner: user in control of the console, or None
    :type owner: str | None
    :param state: ``busy``, ``attached`` or ``closing``
    :type state: str
    :param held_by: why control was refused, or None
    :type held_by: str | None
    """
    message: dict[str, Any] = {
        "type": "status",
        "role": role,
        "owner": owner,
        "state": state,
        "held_by": held_by,
    }
    await ws.send_json(message)


def _dispatch_text(
    text: str,
    on_resize: Callable[[int, int], None] | None,
) -> None:
    """Apply a JSON control message; anything malformed is ignored.

    :param text: text frame from the client
    :type text: str
    :param on_resize: called with ``(rows, cols)``, or None to ignore resizes
    :type on_resize: Callable[[int, int], None] | None
    """
    try:
        message = json.loads(text)
    except ValueError:
        return
    if not isinstance(message, dict) or message.get("type") != "resize":
        return
    rows, cols = message.get("rows"), message.get("cols")
    if on_resize is None or not isinstance(rows, int) or not isinstance(cols, int):
        return
    if rows > 0 and cols > 0:
        on_resize(rows, cols)


async def pump_ws(  # noqa: C901
    ws: WebSocket,
    out: asyncio.Queue[str | None],
    on_input: Callable[[bytes], None] | None,
    on_resize: Callable[[int, int], None] | None,
) -> None:
    """Pump console output to *ws* and client frames to the callbacks.

    Returns when the client disconnects or *out* yields the ``None``
    sentinel. Keepalive pings are protocol-level: ASGI cannot send them, so
    the server sends them (uvicorn ``ws_ping_interval``, 20 s, set in
    ``__main__``); a client that misses its pongs is disconnected, which ends
    this pump.

    :param ws: accepted terminal WebSocket
    :type ws: WebSocket
    :param out: subscriber queue of raw console chunks
    :type out: asyncio.Queue[str | None]
    :param on_input: called with each binary frame; None ignores input
    :type on_input: Callable[[bytes], None] | None
    :param on_resize: called with ``(rows, cols)``; None ignores resizes
    :type on_resize: Callable[[int, int], None] | None
    :raises BaseException: whatever receiving or sending raised; the caller's
        cleanup must run either way
    """

    async def send_output() -> None:
        while (chunk := await out.get()) is not None:
            await ws.send_bytes(chunk.encode("utf-8"))

    async def receive_input() -> None:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                if on_input is not None:
                    on_input(message["bytes"])
            elif message.get("text") is not None:
                _dispatch_text(message["text"], on_resize)

    # An anyio task group, not bare asyncio tasks: Starlette (and TestClient)
    # cancel the endpoint through anyio cancel scopes, and native tasks
    # awaited during that cancellation can leak it past the scope.
    try:
        async with anyio.create_task_group() as group:

            async def until_done(side: Callable[[], Awaitable[None]]) -> None:
                await side()
                group.cancel_scope.cancel()

            group.start_soon(until_done, send_output)
            group.start_soon(until_done, receive_input)
    except BaseExceptionGroup as failures:  # noqa: F821  # builtin on 3.11+
        # One side failed (e.g. a receive error); hand the caller that error.
        first, *_ = failures.exceptions
        raise first from failures
