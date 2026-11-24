"""WebSocket relay between a client and an agent terminal endpoint."""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
from typing import TYPE_CHECKING, Any

import anyio
import websockets
from starlette.websockets import WebSocketDisconnect, WebSocketState

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from starlette.websockets import WebSocket

_log = logging.getLogger(__name__)

# Segments exclude ? and #: a decoded path must never smuggle a query.
TERMINAL_PATH = re.compile(
    r"^(devices/[^/?#]+/consoles/[^/?#]+/terminal"
    r"|devices/[^/?#]+/ssh-terminal|python)$"
)
_SSH_TERMINAL = re.compile(r"^devices/[^/?#]+/ssh-terminal$")
_MODES = frozenset({"view", "control"})
# A close frame's reason may carry at most 123 bytes of UTF-8.
REASON_MAX_BYTES = 123

_now = time.monotonic
_TOUCH_INTERVAL = 60.0
_NORMAL_CLOSE = 1000
_INTERNAL_ERROR = 1011
# Reserved codes that must never be sent in a close frame.
_NO_STATUS = 1005
_ABNORMAL = 1006
_TLS_FAILURE = 1015


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
    return data[:limit].decode("utf-8", "ignore")


def terminal_query(  # pylint: disable=too-many-return-statements
    path: str, raw_query: str
) -> str | None:
    """Build the agent query for *path* from the client's raw query.

    Only ``mode`` is kept, and only as exactly ``view`` or ``control``;
    absent means ``control``, as the portal sends. The ssh terminal takes no
    query at all.

    :param path: a path matching :data:`TERMINAL_PATH`
    :type path: str
    :param raw_query: the client's raw query string
    :type raw_query: str
    :return: the query to send upstream (possibly empty), or None when the
        mode is invalid
    :rtype: str | None
    """
    if _SSH_TERMINAL.match(path):
        return ""
    try:
        params = urllib.parse.parse_qs(
            raw_query, keep_blank_values=True, strict_parsing=bool(raw_query)
        )
    except ValueError:
        return None
    modes = params.get("mode", ["control"])
    if len(modes) != 1 or modes[0] not in _MODES:
        return None
    return urllib.parse.urlencode({"mode": modes[0]})


def origin_allowed(
    origin: str | None, host: str | None, allowed: Iterable[str]
) -> bool:
    """Tell whether a WebSocket handshake's ``Origin`` may open a terminal.

    Browsers apply no CORS to WebSockets, so without this check any page a
    lab user visits could drive a terminal. A client that sends no
    ``Origin`` is not a browser and is let through; a browser is let through
    from the control plane's own origin or from an *allowed* one (the CORS
    origins, ``*`` included).

    :param origin: the handshake's ``Origin`` header, or None
    :type origin: str | None
    :param host: the handshake's ``Host`` header, or None
    :type host: str | None
    :param allowed: origins allowed cross-origin
    :type allowed: Iterable[str]
    :return: True when the connection may proceed
    :rtype: bool
    """
    if origin is None:
        return True
    allowed = set(allowed)
    if "*" in allowed or origin in allowed:
        return True
    return host is not None and urllib.parse.urlsplit(origin).netloc == host


def agent_ws_url(agent_url: str, path: str, query: str) -> str:
    """Build the agent's WebSocket URL from its HTTP base URL.

    :param agent_url: agent base URL, ``http://...`` or ``https://...``
    :type agent_url: str
    :param path: decoded agent endpoint path, without a leading slash; it is
        percent-encoded here
    :type path: str
    :param query: query string built by :func:`terminal_query`, possibly empty
    :type query: str
    :return: matching ``ws://`` or ``wss://`` URL
    :rtype: str
    """
    base = re.sub(r"^http", "ws", agent_url.rstrip("/"), count=1)
    url = f"{base}/{urllib.parse.quote(path.lstrip('/'), safe='/')}"
    return f"{url}?{query}" if query else url


def _sendable_code(code: int | None) -> int:
    """Map an upstream close code to one valid on the wire.

    :param code: close code received from upstream, or None
    :type code: int | None
    :return: code safe to send to the client
    :rtype: int
    """
    if code in (None, _NO_STATUS):
        return _NORMAL_CLOSE
    if code in (_ABNORMAL, _TLS_FAILURE):
        return _INTERNAL_ERROR
    return code


async def _safe_close(client_ws: WebSocket, code: int, reason: str = "") -> None:
    """Close *client_ws* unless it is already closed.

    :param client_ws: client connection
    :type client_ws: WebSocket
    :param code: close code to send
    :type code: int
    :param reason: close reason to send
    :type reason: str
    """
    if WebSocketState.DISCONNECTED in (
        client_ws.application_state,
        client_ws.client_state,
    ):
        return
    try:
        await client_ws.close(code=code, reason=bound_reason(reason))
    except (RuntimeError, WebSocketDisconnect, OSError):
        _log.debug("client websocket already closed")


async def _client_to_upstream(
    client_ws: WebSocket,
    upstream: websockets.ClientConnection,
    touch: Callable[[], None],
) -> None:
    """Forward client frames to upstream until the client disconnects.

    :param client_ws: accepted client WebSocket
    :type client_ws: WebSocket
    :param upstream: open agent connection
    :type upstream: websockets.ClientConnection
    :param touch: notes session activity, rate-limited by the caller
    :type touch: Callable[[], None]
    """
    while True:
        message = await client_ws.receive()
        if message["type"] == "websocket.disconnect":
            return
        touch()
        if message.get("bytes") is not None:
            await upstream.send(message["bytes"])
        elif message.get("text") is not None:
            await upstream.send(message["text"])


async def _upstream_to_client(
    client_ws: WebSocket,
    upstream: websockets.ClientConnection,
    touch: Callable[[], None],
) -> None:
    """Forward upstream frames to the client until upstream closes.

    :param client_ws: accepted client WebSocket
    :type client_ws: WebSocket
    :param upstream: open agent connection
    :type upstream: websockets.ClientConnection
    :param touch: notes session activity, rate-limited by the caller
    :type touch: Callable[[], None]
    """
    async for frame in upstream:
        touch()
        if isinstance(frame, bytes):
            await client_ws.send_bytes(frame)
        else:
            await client_ws.send_text(frame)


async def relay(
    client_ws: WebSocket,
    upstream_url: str,
    headers: dict[str, str],
    on_activity: Callable[[], None],
) -> None:
    """Relay frames between an accepted *client_ws* and *upstream_url*.

    Binary and text frames pass through unchanged. An upstream close is
    mirrored to the client with the same code and reason; a client disconnect
    closes upstream with 1000; a failed upstream connection closes the client
    with 1011. *on_activity* runs at most once per 60 s while frames flow.

    :param client_ws: already accepted client WebSocket
    :type client_ws: WebSocket
    :param upstream_url: ``ws://`` or ``wss://`` URL of the agent endpoint
    :type upstream_url: str
    :param headers: headers to send on the upstream handshake
    :type headers: dict[str, str]
    :param on_activity: callback noting session activity
    :type on_activity: Callable[[], None]
    """
    last_touch = float("-inf")

    def touch() -> None:
        nonlocal last_touch
        now = _now()
        if now - last_touch >= _TOUCH_INTERVAL:
            last_touch = now
            try:
                on_activity()
            except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                _log.exception("websocket activity callback failed")

    try:
        upstream = await websockets.connect(upstream_url, additional_headers=headers)
    except (
        OSError,  # TimeoutError included
        websockets.InvalidHandshake,
        websockets.InvalidURI,
    ) as exc:
        _log.warning("agent websocket connect failed: %s: %s", upstream_url, exc)
        await _safe_close(client_ws, _INTERNAL_ERROR, "agent unreachable")
        return

    try:
        # An anyio task group, not bare asyncio tasks: Starlette (and
        # TestClient) cancel the endpoint through anyio cancel scopes, and
        # native tasks awaited during that cancellation can leak it past it.
        async with anyio.create_task_group() as group:

            async def until_done(
                side: Callable[[WebSocket, websockets.ClientConnection, Callable], Any],
            ) -> None:
                try:
                    await side(client_ws, upstream, touch)
                except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                    # Either side ending, however it ends, ends the relay.
                    _log.debug("websocket relay side %s ended: %r", side.__name__, exc)
                group.cancel_scope.cancel()

            group.start_soon(until_done, _client_to_upstream)
            group.start_soon(until_done, _upstream_to_client)
    finally:
        # Shielded: a cancelled relay must still close the agent socket.
        with anyio.CancelScope(shield=True):
            upstream_code = upstream.close_code
            if upstream_code is None:
                try:
                    await upstream.close(_NORMAL_CLOSE)
                except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                    _log.debug("agent websocket close failed", exc_info=True)
                await _safe_close(client_ws, _NORMAL_CLOSE)
            else:
                await _safe_close(
                    client_ws,
                    _sendable_code(upstream_code),
                    upstream.close_reason or "",
                )
