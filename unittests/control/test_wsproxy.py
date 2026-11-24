"""Tests for the control plane WebSocket relay."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from typing import TYPE_CHECKING

import anyio
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect, WebSocketState

from boardfarm3_control import wsproxy
from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.models import AgentInfo

if TYPE_CHECKING:
    from collections.abc import Iterator


class _FakeClient:
    """Client socket that disconnects after the first upstream frame."""

    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.client_state = WebSocketState.CONNECTED
        self.close_calls: list[int] = []
        self._frames = 0

    async def receive(self) -> dict[str, object]:
        while not self._frames:  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        self.client_state = WebSocketState.DISCONNECTED
        return {"type": "websocket.disconnect", "code": 1001}

    async def send_text(self, _text: str) -> None:
        self._frames += 1

    async def send_bytes(self, _data: bytes) -> None:
        self._frames += 1

    async def close(self, code: int = 1000, reason: str = "") -> None:  # noqa: ARG002
        self.close_calls.append(code)
        raise WebSocketDisconnect(1006)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Upstream:
    """Echo agent stand-in served by a real uvicorn in a thread."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.paths: list[str] = []
        self.raw_paths: list[bytes] = []
        self.connected = threading.Event()
        self.closed_code: int | None = None
        self.app = FastAPI()
        self.app.websocket("/{path:path}")(self._endpoint)
        self.port = _free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.app, host="127.0.0.1", port=self.port, log_level="error"
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    async def _endpoint(self, ws: WebSocket) -> None:
        self.headers = dict(ws.headers)
        self.paths.append(f"{ws.url.path}?{ws.url.query}")
        self.raw_paths.append(ws.scope.get("raw_path") or b"")
        await ws.accept()
        self.connected.set()
        await ws.send_json({"hello": True})
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                self.closed_code = msg.get("code")
                return
            if msg.get("bytes") is not None:
                await ws.send_bytes(msg["bytes"])
            elif msg["text"] == "close":
                await ws.close(code=4409, reason="taken")
                return

    def start(self) -> None:
        self.thread.start()
        while not self.server.started:
            time.sleep(0.01)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(5)


@pytest.fixture
def upstream() -> Iterator[_Upstream]:
    server = _Upstream()
    server.start()
    yield server
    server.stop()


def _client(
    agent_url: str, state: str = "live", cors_origins: list[str] | None = None
) -> tuple[TestClient, list[str]]:
    app = create_app(FakeLauncher(), {"prplos": "img"}, cors_origins=cors_origins)
    app.state.registry.add(
        AgentInfo(
            session_id="s1",
            board_name="b",
            runtime_profile="prplos",
            container_id="c",
            host_port=1,
            created_at=0.0,
            agent_url=agent_url,
            state=state,
        )
    )
    touches: list[str] = []
    app.state.registry.touch = touches.append
    return TestClient(app), touches


_TERMINAL = "/sessions/s1/devices/cpe/consoles/serial/terminal"


def test_relays_binary_and_text(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    with client.websocket_connect(f"{_TERMINAL}?mode=view") as ws:
        assert ws.receive_json() == {"hello": True}
        ws.send_bytes(b"\x00ls\r")
        assert ws.receive_bytes() == b"\x00ls\r"
    assert upstream.paths == ["/devices/cpe/consoles/serial/terminal?mode=view"]


def test_upstream_close_code_propagates(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    with client.websocket_connect(_TERMINAL) as ws:
        ws.receive_json()
        ws.send_text("close")
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_bytes()
    assert exc.value.code == 4409
    assert exc.value.reason == "taken"


def test_sets_session_and_user_headers(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    with client.websocket_connect(
        _TERMINAL, headers={"X-Boardfarm-User": "alice"}
    ) as ws:
        ws.receive_json()
    assert upstream.headers["x-boardfarm-session"] == "s1"
    assert upstream.headers["x-boardfarm-user"] == "alice"


def test_foreign_origin_4403_before_any_upstream(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    with (
        client.websocket_connect(
            "/sessions/s1/python", headers={"Origin": "https://evil.example"}
        ) as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == 4403
    assert upstream.paths == []


@pytest.mark.parametrize(
    ("origin", "cors"),
    [
        ("http://testserver", None),  # same origin as the control plane
        ("https://portal.lab", ["https://portal.lab"]),
        ("https://anything.example", ["*"]),
    ],
)
def test_allowed_origin_is_relayed(
    upstream: _Upstream, origin: str, cors: list[str] | None
) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}", cors_origins=cors)
    with client.websocket_connect(_TERMINAL, headers={"Origin": origin}) as ws:
        assert ws.receive_json() == {"hello": True}


@pytest.mark.parametrize(
    ("origin", "host", "allowed", "expected"),
    [
        (None, "ctl:9000", [], True),
        ("http://ctl:9000", "ctl:9000", [], True),
        ("http://ctl:9001", "ctl:9000", [], False),
        ("https://portal.lab", "ctl:9000", ["https://portal.lab"], True),
        ("https://portal.lab.evil", "ctl:9000", ["https://portal.lab"], False),
        ("https://x.example", "ctl:9000", ["*"], True),
        ("https://x.example", None, [], False),
    ],
)
def test_origin_allowed(
    origin: str | None, host: str | None, allowed: list[str], expected: bool
) -> None:
    assert wsproxy.origin_allowed(origin, host, allowed) is expected


def test_unknown_session_4404() -> None:
    client, _ = _client("http://127.0.0.1:1")
    with (
        client.websocket_connect("/sessions/nope/python") as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == 4404


def test_non_terminal_path_4404(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    with (
        client.websocket_connect("/sessions/s1/devices/cpe/shell") as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == 4404
    assert upstream.paths == []


def test_not_live_4410(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}", state="dead")
    with (
        client.websocket_connect("/sessions/s1/python") as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == 4410


def test_upstream_unreachable_1011() -> None:
    client, _ = _client(f"http://127.0.0.1:{_free_port()}")
    with (
        client.websocket_connect("/sessions/s1/python") as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == 1011


def test_touch_throttled(upstream: _Upstream, monkeypatch: pytest.MonkeyPatch) -> None:
    # Frozen clock: the throttle must not depend on how fast the frames flow.
    monkeypatch.setattr(wsproxy, "_now", lambda: 1000.0)
    client, touches = _client(f"http://127.0.0.1:{upstream.port}")
    with client.websocket_connect(_TERMINAL) as ws:
        ws.receive_json()
        for _ in range(4):
            ws.send_bytes(b"x")
            ws.receive_bytes()
    assert touches == ["s1"]


def test_touch_again_after_interval(
    upstream: _Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    monkeypatch.setattr(wsproxy, "_now", lambda: now[0])
    client, touches = _client(f"http://127.0.0.1:{upstream.port}")
    with client.websocket_connect(_TERMINAL) as ws:
        ws.receive_json()
        ws.send_bytes(b"x")
        ws.receive_bytes()
        now[0] += 61
        ws.send_bytes(b"x")
        ws.receive_bytes()
    assert touches == ["s1", "s1"]


def test_missing_user_header_not_forwarded(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    with client.websocket_connect(_TERMINAL) as ws:
        ws.receive_json()
    assert "x-boardfarm-user" not in upstream.headers


def test_activity_callback_failure_does_not_break_relay(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")

    def boom(_sid: str) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    client.app.state.registry.touch = boom
    with client.websocket_connect(_TERMINAL) as ws:
        ws.receive_json()
        ws.send_bytes(b"x")
        assert ws.receive_bytes() == b"x"


@pytest.mark.asyncio
async def test_client_disconnect_closes_upstream_1000_without_error(
    upstream: _Upstream,
) -> None:
    ws = _FakeClient()
    await wsproxy.relay(
        ws,  # type: ignore[arg-type]
        f"ws://127.0.0.1:{upstream.port}/python",
        {},
        lambda: None,
    )
    for _ in range(100):
        if upstream.closed_code is not None:
            break
        await asyncio.sleep(0.05)
    assert upstream.closed_code == 1000
    assert ws.close_calls == []


class _IdleClient(_FakeClient):
    """Client socket that never sends and never disconnects on its own."""

    async def receive(self) -> dict[str, object]:
        await asyncio.sleep(3600)
        return {"type": "websocket.disconnect", "code": 1000}

    async def close(self, code: int = 1000, reason: str = "") -> None:  # noqa: ARG002
        self.close_calls.append(code)
        self.client_state = WebSocketState.DISCONNECTED


async def _wait_closed(upstream: _Upstream) -> int | None:
    for _ in range(100):
        if upstream.closed_code is not None:
            break
        await asyncio.sleep(0.05)
    return upstream.closed_code


@pytest.mark.asyncio
async def test_exception_in_a_direction_still_closes_upstream(
    upstream: _Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*_args: object) -> None:
        msg = "unexpected"
        raise ValueError(msg)

    monkeypatch.setattr(wsproxy, "_client_to_upstream", broken)
    ws = _IdleClient()
    await wsproxy.relay(
        ws,  # type: ignore[arg-type]
        f"ws://127.0.0.1:{upstream.port}/python",
        {},
        lambda: None,
    )
    assert await _wait_closed(upstream) == 1000
    assert ws.close_calls == [1000]


@pytest.mark.asyncio
async def test_cancelled_relay_closes_upstream(upstream: _Upstream) -> None:
    ws = _IdleClient()
    with anyio.move_on_after(5) as scope:
        async with anyio.create_task_group() as group:
            group.start_soon(
                wsproxy.relay,
                ws,
                f"ws://127.0.0.1:{upstream.port}/python",
                {},
                lambda: None,
            )
            # The hello frame reached the client: the relay is pumping, not
            # still connecting.
            while not ws._frames:  # noqa: ASYNC110
                await asyncio.sleep(0.02)
            group.cancel_scope.cancel()
    assert not scope.cancelled_caught
    assert await _wait_closed(upstream) == 1000


def test_reserved_character_in_device_is_quoted(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    path = "/sessions/s1/devices/my%20cpe/consoles/serial/terminal?mode=view"
    with client.websocket_connect(path) as ws:
        assert ws.receive_json() == {"hello": True}
    assert upstream.raw_paths == [b"/devices/my%20cpe/consoles/serial/terminal"]
    assert upstream.paths == ["/devices/my cpe/consoles/serial/terminal?mode=view"]


def test_encoded_query_in_device_is_not_a_terminal_path(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    path = "/sessions/s1/devices/cpe%3Fmode=control/ssh-terminal"
    with (
        client.websocket_connect(path) as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == 4404
    assert upstream.paths == []


def test_raw_mode_with_fragment_is_rejected(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    with (
        client.websocket_connect(f"{_TERMINAL}?mode=control%23x") as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == 4404
    assert upstream.paths == []


def test_query_is_rebuilt_not_forwarded(upstream: _Upstream) -> None:
    client, _ = _client(f"http://127.0.0.1:{upstream.port}")
    with client.websocket_connect(f"{_TERMINAL}?mode=view&x=1") as ws:
        ws.receive_json()
    with client.websocket_connect(_TERMINAL) as ws:
        ws.receive_json()
    with client.websocket_connect("/sessions/s1/devices/cpe/ssh-terminal?a=b") as ws:
        ws.receive_json()
    assert upstream.paths == [
        "/devices/cpe/consoles/serial/terminal?mode=view",
        "/devices/cpe/consoles/serial/terminal?mode=control",
        "/devices/cpe/ssh-terminal?",
    ]


@pytest.mark.parametrize(
    ("path", "raw", "expected"),
    [
        ("python", "", "mode=control"),
        ("python", "mode=view", "mode=view"),
        ("python", "mode=control", "mode=control"),
        ("python", "mode=control#x", None),
        ("python", "mode=Control", None),
        ("python", "mode=", None),
        ("python", "mode", None),
        ("python", "mode=view&mode=control", None),
        ("python", "mode=view&other=1", "mode=view"),
        ("devices/cpe/ssh-terminal", "mode=control", ""),
    ],
)
def test_terminal_query(path: str, raw: str, expected: str | None) -> None:
    assert wsproxy.terminal_query(path, raw) == expected


def test_agent_ws_url_quotes_the_path() -> None:
    assert (
        wsproxy.agent_ws_url("http://h:1/", "devices/a b/ssh-terminal", "")
        == "ws://h:1/devices/a%20b/ssh-terminal"
    )
    assert (
        wsproxy.agent_ws_url(
            "https://h", "devices/x?y/consoles/c/terminal", "mode=view"
        )
        == "wss://h/devices/x%3Fy/consoles/c/terminal?mode=view"
    )


def test_bound_reason_cuts_on_a_utf8_boundary() -> None:
    reason = "session is " + "\u00e9" * 100
    bounded = wsproxy.bound_reason(reason)
    assert len(bounded.encode()) <= wsproxy.REASON_MAX_BYTES
    assert reason.startswith(bounded)
    assert bounded.encode() == reason.encode()[: len(bounded.encode())]
    assert wsproxy.bound_reason("short") == "short"
