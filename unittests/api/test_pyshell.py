"""Unit tests for the browser Python shell (ptpython over a PTY)."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api import pyshell as pyshell_module
from boardfarm3.api.holds import ALL
from boardfarm3.api.pyshell import ThreadRoutedStream, build_namespace
from boardfarm3.api.session import Session, SessionState
from boardfarm3.exceptions import DeviceNotFound

from ._cat_console import CatConsole
from .conftest import FakeRuntime

if TYPE_CHECKING:
    from collections.abc import Iterator

    from starlette.testclient import WebSocketTestSession

    from boardfarm3.api.runtime import RuntimeOptions

CONTROL = "/python?mode=control"
VIEW = "/python?mode=view"
DEVICE_CONTROL = "/devices/lan/consoles/console/terminal?mode=control"
# ptpython adds these to the namespace while a REPL runs on it.
PTPYTHON_EXTRAS = {"exit", "get_ptpython", "_"}
_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][0-9A-B]|\x1b[=>]")


class _Device:
    """Device stand-in with one interactive ``cat`` console."""

    def __init__(self, console: CatConsole) -> None:
        self.console = console
        self.device_name = "lan"

    def get_interactive_consoles(self) -> dict[str, CatConsole]:
        return {"console": self.console}


class _DeviceManager:
    """Device manager stand-in resolving devices by name or by type."""

    def __init__(self, devices: dict[str, _Device]) -> None:
        self.devices = devices

    def get_device_by_name(self, name: str) -> _Device:
        if name not in self.devices:
            msg = f"No device registered with name {name}"
            raise DeviceNotFound(msg)
        return self.devices[name]

    def get_devices_by_type(self, _device_type: type) -> dict[str, _Device]:
        return dict(self.devices)


class _ShellRuntime(FakeRuntime):
    """``FakeRuntime`` with the attributes the Python shell namespace reads."""

    def __init__(self, options: RuntimeOptions) -> None:
        super().__init__()
        self.options = options
        self.cmdline_args = Namespace(board_name=options.board_name)


class _Env:
    """What a test needs: the client, the session and the device."""

    def __init__(self, client: TestClient, device: _Device) -> None:
        self.client = client
        self.device = device

    @property
    def session(self) -> Session:
        return self.client.app.state.session  # type: ignore[attr-defined]


def _make_env(monkeypatch: pytest.MonkeyPatch, *, legacy: bool) -> Iterator[_Env]:
    console = CatConsole("pyshell_test")
    device = _Device(console)

    def build(session_id: str, options: RuntimeOptions) -> Session:
        options.legacy = legacy
        return Session(session_id, options, runtime=_ShellRuntime(options))

    monkeypatch.setattr(app_module, "build_session", build)
    monkeypatch.delenv(pyshell_module.PYTHON_SHELL_ENV, raising=False)
    application = app_module.create_app("s-test", "board-1")
    try:
        with TestClient(application) as client:
            session = application.state.session
            session.runtime.device_manager = _DeviceManager({"lan": device})
            session.state = SessionState.READY
            yield _Env(client, device)
            if session.pyshell is not None:
                session.pyshell.close()
    finally:
        console.close(force=True)


@pytest.fixture(name="env")
def env_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Env]:
    """Build a READY interact session without ``legacy``.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :yield: the test environment
    :rtype: Iterator[_Env]
    """
    yield from _make_env(monkeypatch, legacy=False)


@pytest.fixture(name="legacy_env")
def legacy_env_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Env]:
    """Build a READY interact session with ``legacy`` set.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :yield: the test environment
    :rtype: Iterator[_Env]
    """
    yield from _make_env(monkeypatch, legacy=True)


_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="pyshell-recv")


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


def _read_until(
    ws: WebSocketTestSession, needle: str, timeout: float = 5, *, answer: bool = True
) -> str:
    """Collect output, escapes stripped, until *needle* appears.

    Answers cursor position requests as xterm.js would, or the prompt waits
    for them.

    :param ws: test WebSocket
    :type ws: WebSocketTestSession
    :param needle: text to wait for
    :type needle: str
    :param timeout: seconds to wait overall
    :type timeout: float
    :param answer: answer CPR queries; False for a viewer
    :type answer: bool
    :return: everything received, decoded and stripped of escapes
    :rtype: str
    """
    seen = ""
    deadline = time.monotonic() + timeout
    while needle not in seen:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail(f"{needle!r} not seen; got {seen[-500:]!r}")
        message = _receive(ws, remaining)
        if message.get("bytes") is not None:
            chunk = message["bytes"].decode(errors="replace")
            if answer and "\x1b[6n" in chunk:
                ws.send_bytes(b"\x1b[1;1R")
            seen += _CSI.sub("", chunk)
    return seen


def _attach(ws: WebSocketTestSession) -> None:
    busy, attached = _status(ws), _status(ws)
    assert (busy["role"], busy["state"]) == ("control", "busy")
    assert (attached["role"], attached["state"]) == ("control", "attached")


def _prompt(ws: WebSocketTestSession) -> None:
    """Wait for the first prompt, so typed input is not lost to start-up."""
    _read_until(ws, ">>>")


def _wait_for(condition: Any, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.02)


def _wait_released(session: Session) -> None:
    _wait_for(lambda: not session.holds.is_held(ALL))


def _closed_code(ws: WebSocketTestSession) -> tuple[int, str]:
    while True:
        message = _receive(ws)
        if message["type"] == "websocket.close":
            return message["code"], message.get("reason", "")


def _user_keys(namespace: dict[str, Any]) -> set[str]:
    return {key for key in namespace if not key.startswith("__")} - PTPYTHON_EXTRAS


def test_namespace_without_legacy(env: _Env) -> None:
    """Without legacy, the namespace offers the device manager and the args."""
    namespace = build_namespace(env.session.runtime)  # type: ignore[arg-type]
    assert _user_keys(namespace) == {"device_manager", "cmdline_args"}
    assert namespace["device_manager"] is env.session.runtime.device_manager
    assert namespace["cmdline_args"] is env.session.runtime.cmdline_args


def test_namespace_with_legacy_exposes_devices(legacy_env: _Env) -> None:
    """With legacy, ``devices.<name>`` is the device."""
    namespace = build_namespace(legacy_env.session.runtime)  # type: ignore[arg-type]
    assert _user_keys(namespace) == {"device_manager", "cmdline_args", "devices"}
    assert namespace["devices"].lan is legacy_env.device


def test_legacy_banner_names_devices(legacy_env: _Env) -> None:
    """A legacy session greets the shell with the CLI's devices banner."""
    with legacy_env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        seen = _read_until(ws, ">>>")
        assert "Use devices.<name> to access one of ['lan']" in seen


def test_eval_and_print_reach_pty(
    env: _Env, capsys: pytest.CaptureFixture[str]
) -> None:
    """print() in the shell reaches the browser, not the agent's stdout."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)
        ws.send_bytes(b"print(6*7)\r")
        assert "42" in _read_until(ws, "42")
    assert "42" not in capsys.readouterr().out


def test_namespace_survives_reattach(env: _Env) -> None:
    """Variables set before a disconnect are there after reconnecting."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)
        ws.send_bytes(b"x = 5\r")
        _wait_for(lambda: env.session.pyshell.namespace.get("x") == 5)  # type: ignore[union-attr]
    _wait_released(env.session)
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)
        ws.send_bytes(b'print(f"x={x}")\r')
        assert "x=5" in _read_until(ws, "x=5")


def test_namespace_dropped_on_release(env: _Env) -> None:
    """Releasing the session drops the shell and its namespace."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)
        ws.send_bytes(b"x = 5\r")
        _wait_for(lambda: env.session.pyshell.namespace.get("x") == 5)  # type: ignore[union-attr]
    shell = env.session.pyshell
    assert shell is not None
    assert shell.namespace["x"] == 5
    assert env.client.delete("/session").status_code == HTTPStatus.OK
    assert env.session.pyshell is None
    assert "x" not in shell.namespace


def test_jobs_refused_while_attached(env: _Env) -> None:
    """While the shell controls, device jobs answer 409 naming the shell."""
    with env.client.websocket_connect(
        CONTROL, headers={"X-Boardfarm-User": "carol"}
    ) as ws:
        _attach(ws)
        resp = env.client.post("/devices/lan/exec", json={"command": "echo x"})
        assert resp.status_code == HTTPStatus.CONFLICT
        assert "held by Python shell" in resp.json()["detail"]
        assert "carol" in resp.json()["detail"]
    _wait_released(env.session)
    resp = env.client.post("/devices/lan/exec", json={"command": "echo after"})
    assert resp.status_code == HTTPStatus.OK


def test_device_terminal_forced_to_view(env: _Env) -> None:
    """A device terminal asking for control is downgraded to view."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        with env.client.websocket_connect(DEVICE_CONTROL) as term:
            status = _status(term)
            assert status["role"] == "view"
            assert "Python shell" in status["held_by"]
        assert not env.session.holds.is_held("lan")


def test_refused_while_device_terminal_controls(env: _Env) -> None:
    """Opening the shell while a device terminal controls closes with 4409."""
    with env.client.websocket_connect(DEVICE_CONTROL) as term:
        _status(term)
        _status(term)
        with env.client.websocket_connect(CONTROL) as ws:
            code, reason = _closed_code(ws)
        assert code == 4409
        assert "held by terminal" in reason
        assert not env.session.holds.is_held(ALL)


def test_second_controller_refused_4409(env: _Env) -> None:
    """Only one connection controls the shell; another gets 4409."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        with env.client.websocket_connect(CONTROL) as second:
            code, reason = _closed_code(second)
        assert code == 4409
        assert "Python shell" in reason


def test_ctrl_c_interrupts_running_statement(env: _Env) -> None:
    """Ctrl+C during a busy statement raises KeyboardInterrupt in it."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)
        ws.send_bytes(b"while True: pass\r")
        shell = env.session.pyshell
        assert shell is not None
        _wait_for(lambda: shell.running_statement)
        ws.send_bytes(b"\x03")
        _read_until(ws, "KeyboardInterrupt", timeout=3)
        _wait_for(lambda: not shell.running_statement)
        ws.send_bytes(b'print("al" + "ive")\r')
        assert "alive" in _read_until(ws, "alive")


def test_disconnect_keeps_hold_until_statement_ends(env: _Env) -> None:
    """A statement left running keeps the hold; it goes when it returns."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)
        ws.send_bytes(b"import time; time.sleep(1.5)\r")
        shell = env.session.pyshell
        assert shell is not None
        _wait_for(lambda: shell.running_statement)
    time.sleep(0.5)
    assert env.session.holds.is_held(ALL)
    _wait_released(env.session)
    assert not shell.running_statement


def test_exit_closes_sockets_and_releases_hold(env: _Env) -> None:
    """exit() ends the REPL: sockets close normally and the hold goes."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)
        ws.send_bytes(b"exit()\r")
        assert _closed_code(ws) == (1000, "Python shell exited")
    _wait_released(env.session)


def test_viewer_mirrors_controller(env: _Env) -> None:
    """A viewer sees the controller's output and its own input is ignored."""
    with env.client.websocket_connect(
        CONTROL, headers={"X-Boardfarm-User": "carol"}
    ) as ws:
        _attach(ws)
        _prompt(ws)
        with env.client.websocket_connect(VIEW) as viewer:
            status = _status(viewer)
            assert (status["role"], status["owner"]) == ("view", "carol")
            assert status["state"] == "attached"
            assert status["held_by"] is None
            viewer.send_bytes(b'print("from" + "viewer")\r')
            time.sleep(0.3)
            ws.send_bytes(b'print("mir" + "rored")\r')
            seen = _read_until(viewer, "mirrored", answer=False)
            assert "fromviewer" not in seen
            assert "fromviewer" not in _read_until(ws, "mirrored")


def test_viewer_without_repl_reports_closing(env: _Env) -> None:
    """A viewer of a shell nobody controls is told no REPL is attached."""
    with env.client.websocket_connect(VIEW) as viewer:
        status = _status(viewer)
        assert (status["role"], status["owner"], status["state"]) == (
            "view",
            None,
            "closing",
        )


def _flood_running_statement(env: _Env, ws: WebSocketTestSession) -> Any:
    """Start a busy statement, then queue more input than the PTY takes.

    :param env: test environment
    :type env: _Env
    :param ws: controlling shell socket
    :type ws: WebSocketTestSession
    :return: the shell's current attach
    :rtype: Any
    """
    # The app's first HTTP request builds its route state (about 1 s); take
    # that hit before timing anything.
    assert env.client.get("/health").status_code == HTTPStatus.OK
    _attach(ws)
    _prompt(ws)
    ws.send_bytes(b"while True: pass\r")
    shell = env.session.pyshell
    assert shell is not None
    _wait_for(lambda: shell.running_statement)
    # Whole lines: a canonical-mode PTY blocks the writer once they fill it.
    chunk = b"#" * 1023 + b"\r"
    for _ in range(80):
        ws.send_bytes(chunk)
    return shell._run


def _health_within(env: _Env, timeout: float) -> None:
    started = time.monotonic()
    try:
        resp = _pool.submit(env.client.get, "/health").result(timeout=timeout)
    except FutureTimeout:
        pytest.fail(f"event loop blocked: /health took over {timeout} s")
    assert resp.status_code == HTTPStatus.OK
    assert time.monotonic() - started < timeout


def test_flooded_input_and_resize_do_not_block_loop(env: _Env) -> None:
    """80 KB typed into a busy statement, then a resize: the loop stays free."""
    with env.client.websocket_connect(CONTROL) as ws:
        _flood_running_statement(env, ws)
        ws.send_text(json.dumps({"type": "resize", "rows": 40, "cols": 132}))
        time.sleep(0.5)
        _health_within(env, 1)


def test_release_after_flooded_detach_is_prompt(env: _Env) -> None:
    """Detached with input stuck in a full PTY, release still ends it quickly."""
    with env.client.websocket_connect(CONTROL) as ws:
        run = _flood_running_statement(env, ws)
        before = os.fstat(run.master)
    time.sleep(0.3)
    started = time.monotonic()
    assert env.client.delete("/session").status_code == HTTPStatus.OK
    assert time.monotonic() - started < 2
    assert run.master_closed
    assert not run.thread.is_alive()
    try:
        after = os.fstat(run.master)
    except OSError:
        return
    # The fd number was reused by something else: not the PTY any more.
    assert (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)


def test_hold_kept_for_line_typed_just_before_close(env: _Env) -> None:
    """A line sent right before closing runs before the ALL hold goes."""
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)
        ws.send_bytes(b"import time\r")
        ws.send_bytes(b"x=sum(range(10**8))\r")
    shell = env.session.pyshell
    assert shell is not None
    deadline = time.monotonic() + 30
    while env.session.holds.is_held(ALL):
        assert time.monotonic() < deadline, "hold never released"
        time.sleep(0.01)
    # Released only after the statement finished.
    assert shell.namespace.get("x") == sum(range(10**8))
    assert not shell.running_statement


def test_disabled_closes_4403(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """The kill switch closes the shell endpoint with 4403."""
    monkeypatch.setenv(pyshell_module.PYTHON_SHELL_ENV, "0")
    with env.client.websocket_connect(CONTROL) as ws:
        code, _ = _closed_code(ws)
    assert code == 4403
    assert env.session.pyshell is None


def test_not_ready_closes_4423(env: _Env) -> None:
    """A session that is not READY closes with 4423."""
    env.session.state = SessionState.BOOTING
    with env.client.websocket_connect(CONTROL) as ws:
        code, _ = _closed_code(ws)
    assert code == 4423


def test_failed_session_opens_the_shell(env: _Env) -> None:
    """A session whose boot failed still opens the Python shell, for debugging."""
    env.session.state = SessionState.FAILED
    with env.client.websocket_connect(CONTROL) as ws:
        _attach(ws)
        _prompt(ws)


def test_release_closes_shell_4410(env: _Env) -> None:
    """Releasing the session closes every shell socket with 4410."""
    with (
        env.client.websocket_connect(CONTROL) as ws,
        env.client.websocket_connect(VIEW) as viewer,
    ):
        _attach(ws)
        _status(viewer)
        shell = env.session.pyshell
        assert shell is not None
        assert env.client.delete("/session").status_code == HTTPStatus.OK
        for sock in (ws, viewer):
            assert _closed_code(sock)[0] == 4410
    assert not env.session.holds.is_held(ALL)
    assert not shell.running_statement
    assert shell.repl_thread is None or not shell.repl_thread.is_alive()


def test_thread_routed_stream_routes_by_thread() -> None:
    """Writes from a registered thread go to its file, others to the original."""

    class _Sink:
        def __init__(self) -> None:
            self.data = ""

        def write(self, text: str) -> int:
            self.data += text
            return len(text)

        def flush(self) -> None:
            pass

    original, routed = _Sink(), _Sink()
    stream = ThreadRoutedStream(original)

    def run() -> None:
        stream.route(routed)
        try:
            stream.write("in thread")
        finally:
            stream.unroute()

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    stream.write("main")
    assert (original.data, routed.data) == ("main", "in thread")


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "No", "off", " Off "])
def test_disabled_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """0, false, no and off disable the shell, in any case."""
    monkeypatch.setenv(pyshell_module.PYTHON_SHELL_ENV, value)
    assert not pyshell_module.python_shell_enabled()


@pytest.mark.parametrize("value", [None, "", "1", "true", "yes", "on"])
def test_enabled_values(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """Unset or any other value leaves the shell enabled."""
    if value is None:
        monkeypatch.delenv(pyshell_module.PYTHON_SHELL_ENV, raising=False)
    else:
        monkeypatch.setenv(pyshell_module.PYTHON_SHELL_ENV, value)
    assert pyshell_module.python_shell_enabled()


def test_disabled_by_word_closes_4403(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The word off closes the endpoint like 0."""
    monkeypatch.setenv(pyshell_module.PYTHON_SHELL_ENV, "off")
    with env.client.websocket_connect(CONTROL) as ws:
        code, _ = _closed_code(ws)
    assert code == 4403
