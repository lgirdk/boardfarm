"""Unit tests for the shared-console terminal WebSocket endpoint."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import select
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pexpect
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from boardfarm3.api import app as app_module
from boardfarm3.api.holds import ALL
from boardfarm3.api.session import Session, SessionState
from boardfarm3.api.terminal_io import pump_ws, send_status
from boardfarm3.exceptions import DeviceNotFound

from ._cat_console import CatConsole
from .conftest import FakeRuntime

if TYPE_CHECKING:
    from collections.abc import Iterator

    from starlette.testclient import WebSocketTestSession

    from boardfarm3.api.runtime import RuntimeOptions

TERMINAL = "/devices/lan/consoles/console/terminal"
CONTROL = f"{TERMINAL}?mode=control"
VIEW = f"{TERMINAL}?mode=view"
SHELL_REASON = "session held by Python shell (user carol)"


class _Device:
    """``LinuxDevice`` stand-in exposing one interactive console."""

    def __init__(self, console: CatConsole) -> None:
        self.console = console

    def get_interactive_consoles(self) -> dict[str, CatConsole]:
        return {"console": self.console}


class _DeviceManager:
    """Device manager stand-in resolving devices by name."""

    def __init__(self, devices: dict[str, _Device]) -> None:
        self.devices = devices

    def get_device_by_name(self, name: str) -> _Device:
        if name not in self.devices:
            msg = f"No device registered with name {name}"
            raise DeviceNotFound(msg)
        return self.devices[name]


class _Env:
    """What a test needs: the client, the session and the console."""

    def __init__(self, client: TestClient, console: CatConsole) -> None:
        self.client = client
        self.console = console

    @property
    def session(self) -> Session:
        return self.client.app.state.session  # type: ignore[attr-defined]


@pytest.fixture(name="env")
def env_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Env]:
    """Build a READY interact session whose ``lan`` console is ``cat``.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :yield: the test environment
    :rtype: Iterator[_Env]
    """
    console = CatConsole("terminal_test")

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=FakeRuntime())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    try:
        with TestClient(application) as client:
            session = application.state.session
            session.runtime.device_manager = _DeviceManager(
                {"lan": _Device(console)},
            )
            session.state = SessionState.READY
            yield _Env(client, console)
    finally:
        console.close(force=True)


_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ws-recv")


def _receive(ws: WebSocketTestSession, timeout: float = 5) -> dict[str, Any]:
    # TestClient's receive blocks forever; bound it so a failure cannot hang.
    try:
        return _pool.submit(ws.receive).result(timeout=timeout)
    except FutureTimeout:
        pytest.fail("no WebSocket message within the timeout")


def _status(ws: WebSocketTestSession) -> dict[str, Any]:
    message = _receive(ws)
    assert message.get("text") is not None, message
    data = json.loads(message["text"])
    assert data["type"] == "status"
    return data


def _read_until(ws: WebSocketTestSession, needle: str, timeout: float = 5) -> str:
    """Collect binary output until *needle* appears.

    :param ws: test WebSocket
    :type ws: WebSocketTestSession
    :param needle: text to wait for
    :type needle: str
    :param timeout: seconds to wait overall
    :type timeout: float
    :return: everything received, decoded
    :rtype: str
    """
    seen = ""
    deadline = time.monotonic() + timeout
    while needle not in seen:
        message = _receive(ws, max(deadline - time.monotonic(), 0.01))
        if message.get("bytes") is not None:
            seen += message["bytes"].decode()
    return seen


def _attach(ws: WebSocketTestSession) -> None:
    assert _status(ws)["state"] == "busy"
    assert _status(ws)["state"] == "attached"


def _wait_released(session: Session, timeout: float = 2) -> None:
    deadline = time.monotonic() + timeout
    while session.holds.held_reason(frozenset({"lan"})) is not None:
        assert time.monotonic() < deadline, "hold still in place"
        time.sleep(0.02)


def test_input_burst_echoes_in_order(env: _Env) -> None:
    """200 one-byte frames all echo back, in order, within 2 s."""
    payload = "".join(chr(ord("a") + i % 26) for i in range(199))
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        start = time.monotonic()
        for char in payload + "\n":
            ws.send_bytes(char.encode())
        seen = _read_until(ws, payload, timeout=2)
        assert time.monotonic() - start < 2
        assert payload in seen


def test_input_split_multibyte_character(env: _Env) -> None:
    """A UTF-8 character split across two frames reaches the console whole."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        encoded = "caf\u00e9\n".encode()
        ws.send_bytes(encoded[:4])
        ws.send_bytes(encoded[4:])
        assert "caf\u00e9" in _read_until(ws, "caf\u00e9")


def test_viewer_learns_controller_owner(env: _Env) -> None:
    """Viewers are told who controls the console, and when nobody does."""
    with env.client.websocket_connect(
        VIEW, headers={"X-Boardfarm-User": "victor"}
    ) as viewer:
        first = _status(viewer)
        assert (first["role"], first["owner"]) == ("view", None)
        with env.client.websocket_connect(
            CONTROL, headers={"X-Boardfarm-User": "alice"}
        ) as ctl:
            _attach(ctl)
            told = _status(viewer)
            assert (told["role"], told["owner"]) == ("view", "alice")
        left = _status(viewer)
        assert (left["role"], left["owner"]) == ("view", None)


def test_hand_over_tells_everyone_new_owner(env: _Env) -> None:
    """On hand-over, the demoted controller and the viewers learn the new owner."""
    with (
        env.client.websocket_connect(VIEW) as viewer,
        env.client.websocket_connect(
            CONTROL, headers={"X-Boardfarm-User": "alice"}
        ) as alice,
    ):
        _status(viewer)
        _attach(alice)
        assert _status(viewer)["owner"] == "alice"
        with env.client.websocket_connect(
            CONTROL, headers={"X-Boardfarm-User": "bob"}
        ) as bob:
            demoted = _status(alice)
            assert (demoted["role"], demoted["owner"]) == ("view", "bob")
            seen = _status(viewer)
            assert (seen["role"], seen["owner"]) == ("view", "bob")
            mine = _status(bob)
            assert (mine["role"], mine["owner"], mine["state"]) == (
                "control",
                "bob",
                "attached",
            )


def test_connection_after_console_eof_closes_4410(env: _Env) -> None:
    """A late connection to a console that hit EOF is refused, not attached."""
    with env.client.websocket_connect(VIEW) as viewer:
        _status(viewer)
        with env.client.websocket_connect(CONTROL) as ctl:
            _attach(ctl)
            # The viewer keeps the dead terminal registered while we connect.
            env.console.sendeof()
            deadline = time.monotonic() + 5
            term = env.session.terminals._terminals[("lan", "console")]
            while not term.dead:
                assert time.monotonic() < deadline
                time.sleep(0.02)
            with env.client.websocket_connect(CONTROL) as late:
                message = _receive(late)
            assert message.get("code") == 4410, message


def test_control_echoes_input(env: _Env) -> None:
    """Control input reaches the console and its output comes back."""
    with env.client.websocket_connect(CONTROL) as ws:
        busy, attached = _status(ws), _status(ws)
        assert (busy["role"], busy["state"]) == ("control", "busy")
        assert (attached["role"], attached["state"]) == ("control", "attached")
        ws.send_bytes(b"hello\n")
        assert "hello" in _read_until(ws, "hello")


def test_owner_comes_from_user_header(env: _Env) -> None:
    """The status owner and the hold reason name the X-Boardfarm-User."""
    with env.client.websocket_connect(
        CONTROL, headers={"X-Boardfarm-User": "alice"}
    ) as ws:
        assert _status(ws)["owner"] == "alice"
        _status(ws)
        assert env.session.holds.reason("lan") == (
            "device lan held by terminal (user alice)"
        )


def test_exec_refused_while_attached_and_works_after_close(env: _Env) -> None:
    """The terminal holds the device: exec is 409 until the socket closes."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        resp = env.client.post("/devices/lan/exec", json={"command": "echo x"})
        assert resp.status_code == HTTPStatus.CONFLICT
        assert "held by terminal" in resp.json()["detail"]
    _wait_released(env.session)
    resp = env.client.post("/devices/lan/exec", json={"command": "echo after"})
    assert resp.status_code == HTTPStatus.OK


def test_viewer_mirrors_controller_output(env: _Env) -> None:
    """A viewer sees the controller's output; its own input is ignored."""
    with env.client.websocket_connect(CONTROL) as ctl:
        _attach(ctl)
        with env.client.websocket_connect(VIEW) as viewer:
            status = _status(viewer)
            assert (status["role"], status["state"]) == ("view", "attached")
            viewer.send_bytes(b"fromviewer\n")
            time.sleep(0.3)
            ctl.send_bytes(b"mirrored\n")
            seen = _read_until(viewer, "mirrored")
            assert "fromviewer" not in seen
            assert "fromviewer" not in _read_until(ctl, "mirrored")


def test_viewer_sees_api_job_output(env: _Env) -> None:
    """With no controller, a viewer still sees what an API job reads."""
    with env.client.websocket_connect(VIEW) as viewer:
        assert _status(viewer)["role"] == "view"
        resp = env.client.post("/devices/lan/exec", json={"command": "echo apiout"})
        assert resp.status_code == HTTPStatus.OK
        assert "apiout" in _read_until(viewer, "apiout")
    assert env.session.holds.held_reason(frozenset({"lan"})) is None


def test_second_control_takes_over(env: _Env) -> None:
    """A second controller takes over; the first drops to view."""
    with env.client.websocket_connect(
        CONTROL, headers={"X-Boardfarm-User": "alice"}
    ) as first:
        _attach(first)
        with env.client.websocket_connect(
            CONTROL, headers={"X-Boardfarm-User": "bob"}
        ) as second:
            demoted = _status(first)
            assert demoted["role"] == "view"
            taken = _status(second)
            assert (taken["role"], taken["state"]) == ("control", "attached")
            assert env.session.holds.reason("lan") == (
                "device lan held by terminal (user bob)"
            )
            first.send_bytes(b"fromold\n")
            time.sleep(0.3)
            second.send_bytes(b"fromnew\n")
            assert "fromold" not in _read_until(second, "fromnew")


def test_replaced_controller_disconnect_keeps_hold(env: _Env) -> None:
    """Only the current controller's disconnect releases the hold."""
    with env.client.websocket_connect(CONTROL) as first:
        _attach(first)
        with env.client.websocket_connect(CONTROL) as second:
            assert _status(first)["role"] == "view"
            assert _status(second)["state"] == "attached"
            first.close()
            time.sleep(0.5)
            assert env.session.holds.is_held("lan")
            second.send_bytes(b"stillworks\n")
            assert "stillworks" in _read_until(second, "stillworks")
    _wait_released(env.session)


def test_python_shell_hold_downgrades_control_to_view(env: _Env) -> None:
    """A control request while the Python shell holds ALL becomes a viewer."""
    env.session.holds.hold(ALL, SHELL_REASON)
    with env.client.websocket_connect(CONTROL) as ws:
        status = _status(ws)
        assert status["role"] == "view"
        assert status["held_by"] == SHELL_REASON
        assert not env.session.holds.is_held("lan")
    assert env.session.holds.reason(ALL) == SHELL_REASON


def test_abrupt_disconnect_releases_hold(env: _Env) -> None:
    """Leaving the socket through an exception still releases the hold."""
    with pytest.raises(RuntimeError, match="tab died"):  # noqa: PT012, SIM117
        with env.client.websocket_connect(CONTROL) as ws:
            _attach(ws)
            ws.close()
            msg = "tab died"
            raise RuntimeError(msg)
    _wait_released(env.session)
    resp = env.client.post("/devices/lan/exec", json={"command": "echo after"})
    assert resp.status_code == HTTPStatus.OK


def test_receive_error_releases_hold(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receive that raises (a dropped TCP link) still releases the hold."""
    original = WebSocket.receive

    async def flaky(self: WebSocket) -> dict[str, Any]:
        message = await original(self)
        if message.get("bytes") == b"boom":
            msg = "connection reset"
            raise OSError(msg)
        return message

    monkeypatch.setattr(WebSocket, "receive", flaky)
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        ws.send_bytes(b"boom")
        _wait_released(env.session)


def test_close_does_not_send_interrupt(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing the terminal leaves the console alone: no Ctrl+C, no newline."""
    calls: list[str] = []
    monkeypatch.setattr(
        env.console, "sendcontrol", lambda char: calls.append(f"ctrl:{char}")
    )
    monkeypatch.setattr(
        env.console, "sendline", lambda line="": calls.append(f"line:{line}")
    )
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        ws.send_bytes(b"typed\n")
        _read_until(ws, "typed")
    _wait_released(env.session)
    assert calls == []


def test_unknown_console_closes_4404(env: _Env) -> None:
    """An unknown console closes with 4404."""
    path = "/devices/lan/consoles/nope/terminal?mode=control"
    with env.client.websocket_connect(path) as ws:
        message = _receive(ws)
    assert (message["type"], message["code"]) == ("websocket.close", 4404)


def test_unknown_device_closes_4404(env: _Env) -> None:
    """An unknown device closes with 4404."""
    path = "/devices/wan/consoles/console/terminal?mode=view"
    with env.client.websocket_connect(path) as ws:
        message = _receive(ws)
    assert (message["type"], message["code"]) == ("websocket.close", 4404)


def test_not_ready_closes_4423(env: _Env) -> None:
    """A session that is not READY closes with 4423."""
    env.session.state = SessionState.BOOTING
    with env.client.websocket_connect(CONTROL) as ws:
        message = _receive(ws)
    assert (message["type"], message["code"]) == ("websocket.close", 4423)


def test_failed_session_attaches(env: _Env) -> None:
    """A session whose boot failed still takes a terminal, for debugging."""
    env.session.state = SessionState.FAILED
    with env.client.websocket_connect(CONTROL) as ws:
        status = _status(ws)
    assert status["role"] == "control"


def test_non_interact_session_closes_4423(env: _Env) -> None:
    """A session in a non-interact mode closes with 4423."""
    env.session.mode = "pytest"
    with env.client.websocket_connect(CONTROL) as ws:
        message = _receive(ws)
    assert (message["type"], message["code"]) == ("websocket.close", 4423)


def test_release_closes_terminals_4410(env: _Env) -> None:
    """Releasing the session closes every terminal with 4410."""
    with (
        env.client.websocket_connect(CONTROL) as ctl,
        env.client.websocket_connect(VIEW) as viewer,
    ):
        _attach(ctl)
        _status(viewer)
        assert env.client.delete("/session").status_code == HTTPStatus.OK
        for ws in (ctl, viewer):
            with pytest.raises(WebSocketDisconnect) as closed:  # noqa: PT012
                while True:
                    ws.receive_bytes()
            assert closed.value.code == 4410
    assert env.session.holds.held_reason(frozenset({"lan"})) is None


def test_console_eof_closes_4410(env: _Env) -> None:
    """The console dying (EOF) closes the controller with 4410."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        env.console.sendeof()
        with pytest.raises(WebSocketDisconnect) as closed:  # noqa: PT012
            while True:
                _pool.submit(ws.receive_bytes).result(timeout=5)
        assert closed.value.code == 4410
    _wait_released(env.session)


class _FakeWS:
    """Just enough of a Starlette WebSocket for ``pump_ws``."""

    def __init__(self, incoming: list[dict[str, Any] | Exception]) -> None:
        self.incoming = incoming
        self.sent: list[dict[str, Any]] = []

    async def receive(self) -> dict[str, Any]:
        await asyncio.sleep(0.01)
        if not self.incoming:
            await asyncio.sleep(3600)
        item = self.incoming.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append({"bytes": data})

    async def send_json(self, data: Any) -> None:
        self.sent.append({"json": data})


async def test_pump_dispatches_input_and_resize() -> None:
    """Binary frames go to on_input, resize messages to on_resize."""
    ws = _FakeWS(
        [
            {"type": "websocket.receive", "bytes": b"ls\n"},
            {
                "type": "websocket.receive",
                "text": '{"type":"resize","cols":80,"rows":24}',
            },
            {"type": "websocket.receive", "text": "not json"},
            {"type": "websocket.disconnect", "code": 1000},
        ]
    )
    inputs: list[bytes] = []
    sizes: list[tuple[int, int]] = []
    out: asyncio.Queue[str | None] = asyncio.Queue()
    await asyncio.wait_for(
        pump_ws(ws, out, inputs.append, lambda r, c: sizes.append((r, c))),  # type: ignore[arg-type]
        timeout=2,
    )
    assert inputs == [b"ls\n"]
    assert sizes == [(24, 80)]


async def test_pump_forwards_output_until_sentinel() -> None:
    """Queued chunks are sent as bytes; the None sentinel ends the pump."""
    ws = _FakeWS([])
    out: asyncio.Queue[str | None] = asyncio.Queue()
    for item in ("a", "b", None):
        out.put_nowait(item)
    await asyncio.wait_for(pump_ws(ws, out, None, None), timeout=2)  # type: ignore[arg-type]
    assert ws.sent == [{"bytes": b"a"}, {"bytes": b"b"}]


async def test_pump_ignores_input_without_callbacks() -> None:
    """A view pump (no callbacks) drops input and resize frames."""
    ws = _FakeWS(
        [
            {"type": "websocket.receive", "bytes": b"x"},
            {
                "type": "websocket.receive",
                "text": '{"type":"resize","cols":1,"rows":1}',
            },
            {"type": "websocket.disconnect", "code": 1000},
        ]
    )
    await asyncio.wait_for(pump_ws(ws, asyncio.Queue(), None, None), timeout=2)  # type: ignore[arg-type]


async def test_pump_receive_error_propagates() -> None:
    """A receive error ends the pump by raising, so the caller cleans up."""
    ws = _FakeWS([OSError("reset")])
    with pytest.raises(OSError, match="reset"):
        await asyncio.wait_for(pump_ws(ws, asyncio.Queue(), None, None), timeout=2)  # type: ignore[arg-type]


async def test_send_status_shape() -> None:
    """Status messages carry type, role, owner, state and optional held_by."""
    ws = _FakeWS([])
    await send_status(ws, "view", "bob", "attached")  # type: ignore[arg-type]
    await send_status(ws, "view", None, "attached", held_by="shell")  # type: ignore[arg-type]
    assert ws.sent == [
        {
            "json": {
                "type": "status",
                "role": "view",
                "owner": "bob",
                "state": "attached",
                "held_by": None,
            }
        },
        {
            "json": {
                "type": "status",
                "role": "view",
                "owner": None,
                "state": "attached",
                "held_by": "shell",
            }
        },
    ]


class _StuckConsole:
    """Console whose input never drains: its fd is a pipe nobody reads."""

    name = "stuck"

    def __init__(self) -> None:
        self.read_fd, self.child_fd = os.pipe()

    def add_raw_listener(self, _listener: Any) -> None:
        pass

    def remove_raw_listener(self, _listener: Any) -> None:
        pass

    def read_nonblocking(self, _size: int, timeout: float) -> bytes:
        time.sleep(timeout)
        msg = "nothing"
        raise pexpect.TIMEOUT(msg)

    def isalive(self) -> bool:
        return True

    def setwinsize(self, _rows: int, _cols: int) -> None:
        pass

    def drain(self) -> int:
        """Read whatever the pipe holds; return how many bytes."""
        total = 0
        while select.select([self.read_fd], [], [], 0)[0]:
            chunk = os.read(self.read_fd, 1 << 16)
            if not chunk:
                break
            total += len(chunk)
        return total

    def close(self) -> None:
        os.close(self.read_fd)
        os.close(self.child_fd)


def _writer_threads() -> list[threading.Thread]:
    return [
        thread
        for thread in threading.enumerate()
        if thread.name == "terminal-in-stuck" and thread.is_alive()
    ]


def test_detach_after_big_paste_into_stuck_console(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A >1 MB paste into a console that never drains does not stall detach.

    The loop stays responsive while the terminal closes, the hold goes only
    once the writer thread has ended, and nothing is written after that.
    """
    stuck = _StuckConsole()
    env.session.runtime.device_manager = _DeviceManager({"lan": _Device(stuck)})
    flags = fcntl.fcntl(stuck.child_fd, fcntl.F_GETFL)
    writer_alive_at_release: list[bool] = []
    original_release = env.session.holds.release

    def release(name: str) -> None:
        writer_alive_at_release.append(bool(_writer_threads()))
        original_release(name)

    monkeypatch.setattr(env.session.holds, "release", release)
    try:
        ws_cm = env.client.websocket_connect(CONTROL)
        ws = ws_cm.__enter__()
        _attach(ws)
        chunk = b"x" * (1 << 16)
        for _ in range(20):  # 1.25 MB, far beyond the 64 KiB pipe buffer
            ws.send_bytes(chunk)
        # Wait until the writer has filled the pipe and is stuck on it.
        deadline = time.monotonic() + 5
        while not select.select([stuck.read_fd], [], [], 0)[0]:
            assert time.monotonic() < deadline, "writer never wrote"
            time.sleep(0.01)
        time.sleep(0.2)
        # Warm up: the first /health of a session is slow on its own.
        assert env.client.get("/health").status_code == HTTPStatus.OK
        closing = threading.Thread(target=ws_cm.__exit__, args=(None, None, None))
        closing.start()
        start = time.monotonic()
        assert env.client.get("/health").status_code == HTTPStatus.OK
        assert time.monotonic() - start < 1
        closing.join(5)
        assert not closing.is_alive(), "detach did not finish"
        _wait_released(env.session)
        assert writer_alive_at_release == [False]
        assert not _writer_threads()
        # Nothing is typed after the release, even once there is room.
        stuck.drain()
        time.sleep(0.3)
        assert stuck.drain() == 0
        # The fd got its original (blocking) flags back.
        assert fcntl.fcntl(stuck.child_fd, fcntl.F_GETFL) == flags
    finally:
        stuck.close()


def test_mismatched_session_websocket_closes_4409(env: _Env) -> None:
    """SessionGuard refuses a WebSocket addressed to another session."""
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        env.client.websocket_connect(
            CONTROL, headers={"X-Boardfarm-Session": "s-other"}
        ) as ws,
    ):
        ws.receive()
    assert exc.value.code == 4409
    assert exc.value.reason == "session mismatch"
    assert not env.session.holds.is_held("lan")


def test_matching_session_websocket_is_served(env: _Env) -> None:
    """The right X-Boardfarm-Session header passes the guard."""
    with env.client.websocket_connect(
        CONTROL, headers={"X-Boardfarm-Session": "s-test"}
    ) as ws:
        _attach(ws)


def test_long_multibyte_reason_fits_a_close_frame(env: _Env) -> None:
    """A close reason naming a long multibyte device stays within 123 bytes."""
    device = "é" * 100
    with env.client.websocket_connect(f"/devices/{device}/ssh-terminal") as ws:
        message = _receive(ws)
    assert message["type"] == "websocket.close"
    assert message["code"] == 4404
    reason = message["reason"]
    assert reason.startswith("no device")
    assert len(reason.encode()) <= 123
