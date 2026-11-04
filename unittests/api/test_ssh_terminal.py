"""Unit tests for the extra ssh terminals of a device."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pexpect
import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.session import Session, SessionState
from boardfarm3.api.terminal import max_ssh_terminals, ssh_terminal_eligible
from boardfarm3.devices.base_devices import linux_device
from boardfarm3.devices.base_devices.linux_device import LinuxDevice
from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.connections.ssh_connection import SSHConnection
from boardfarm3.templates.cpe import CPE

from ._cat_console import CatConsole
from .conftest import FakeRuntime
from .test_terminal import _DeviceManager, _read_until, _receive, _status

if TYPE_CHECKING:
    from collections.abc import Iterator

    from starlette.testclient import WebSocketTestSession

    from boardfarm3.api.runtime import RuntimeOptions

SSH = "/devices/lan/ssh-terminal"


class _Manager(_DeviceManager):
    def get_devices_by_type(self, _kind: type) -> dict[str, Any]:
        return self.devices


class _SshDevice:
    """Eligible ``LinuxDevice`` stand-in handing out ``cat`` spawns."""

    def __init__(self, connection_type: str = "ssh_connection") -> None:
        self._config = {"connection_type": connection_type}
        self.opened: list[CatConsole] = []
        self.names: list[str] = []
        self.fail: Exception | None = None

    def get_interactive_consoles(self) -> dict[str, Any]:
        return {"console": object()}

    def open_extra_console(self, name: str) -> CatConsole:
        if self.fail is not None:
            raise self.fail
        spawn = CatConsole(name)
        self.opened.append(spawn)
        self.names.append(name)
        return spawn


class _Env:
    def __init__(self, client: TestClient, device: _SshDevice) -> None:
        self.client = client
        self.device = device

    @property
    def session(self) -> Session:
        return self.client.app.state.session  # type: ignore[attr-defined]


@pytest.fixture(name="env")
def env_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Env]:
    """Build a READY interact session whose ``lan`` allows ssh terminals.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :yield: the test environment
    :rtype: Iterator[_Env]
    """
    device = _SshDevice()

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=FakeRuntime())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    try:
        with TestClient(application) as client:
            session = application.state.session
            session.runtime.device_manager = _Manager({"lan": device})
            session.state = SessionState.READY
            yield _Env(client, device)
    finally:
        for spawn in device.opened:
            spawn.close(force=True)


def _connect(env: _Env) -> Any:
    return env.client.websocket_connect(SSH, headers={"X-Boardfarm-User": "alice"})


def _attached(ws: WebSocketTestSession) -> dict[str, Any]:
    """Read the busy and attached statuses a new ssh terminal sends.

    :param ws: test WebSocket
    :type ws: WebSocketTestSession
    :return: the attached status
    :rtype: dict[str, Any]
    """
    assert _status(ws)["state"] == "busy"
    return _status(ws)


def _closes_with(ws: WebSocketTestSession) -> int:
    message = _receive(ws)
    while message["type"] == "websocket.send" and message.get("bytes") is not None:
        message = _receive(ws)  # skip output
    assert message["type"] == "websocket.close", message
    return message["code"]


def _wait(predicate: Any, timeout: float = 5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_eligibility() -> None:
    """Only non-CPE ssh devices with a console are eligible."""
    assert ssh_terminal_eligible(_SshDevice()) is True
    assert ssh_terminal_eligible(_SshDevice("authenticated_ssh")) is True
    for kind in ("ser2net", "telnet", "ldap_authenticated_serial"):
        assert ssh_terminal_eligible(_SshDevice(kind)) is False

    class _Cpe(CPE, _SshDevice):  # type: ignore[misc]
        def __init__(self) -> None:  # pylint: disable=super-init-not-called
            _SshDevice.__init__(self)

    _Cpe.__abstractmethods__ = frozenset()  # instantiate without the template body
    assert ssh_terminal_eligible(_Cpe()) is False
    no_console = _SshDevice()
    no_console.get_interactive_consoles = dict  # type: ignore[method-assign]
    assert ssh_terminal_eligible(no_console) is False
    assert ssh_terminal_eligible(_NoOpen()) is False


class _NoOpen:
    """A device without ``open_extra_console``."""

    _config = {"connection_type": "ssh_connection"}  # noqa: RUF012

    def get_interactive_consoles(self) -> dict[str, Any]:
        return {"console": object()}


def test_devices_lists_ssh_terminals_flag(env: _Env) -> None:
    """``GET /devices`` flags devices that offer ssh terminals."""
    listed = env.client.get("/devices").json()["devices"]
    assert [(d["name"], d["ssh_terminals"]) for d in listed] == [("lan", True)]


def test_each_connection_opens_distinct_spawn_and_closes_it(env: _Env) -> None:
    """Two sockets get two spawns, both closed on exit."""
    with _connect(env) as one, _connect(env) as two:
        status = _attached(one)
        assert status["role"] == "control"
        assert status["owner"] == "alice"
        assert status["state"] == "attached"
        _attached(two)
        assert len(env.device.opened) == 2
        assert env.device.opened[0] is not env.device.opened[1]
        # Both logins run in threads, so their order is not fixed.
        assert sorted(env.device.names) == ["lan.term1", "lan.term2"]
        one.send_bytes(b"one\n")
        assert "one" in _read_until(one, "one")
    assert _wait(lambda: all(s.closed for s in env.device.opened))


def test_not_affected_by_device_hold(env: _Env) -> None:
    """A device hold does not stop an ssh terminal."""
    env.session.queue.holds.hold("lan", "held by someone")
    with _connect(env) as ws:
        _attached(ws)
        ws.send_bytes(b"hello\n")
        assert "hello" in _read_until(ws, "hello")


def test_limit_closes_4429(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """The terminal beyond the limit is refused with 4429."""
    monkeypatch.setenv("BOARDFARM_MAX_SSH_TERMINALS", "1")
    with _connect(env) as first:
        _attached(first)
        with _connect(env) as second:
            assert _closes_with(second) == 4429
    # A closed terminal frees its slot, and its number is not reused.
    assert _wait(lambda: env.device.opened[0].closed)
    with _connect(env) as third:
        _attached(third)
    assert env.device.names == ["lan.term1", "lan.term2"]


def test_limit_is_per_device(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """One device at its limit does not block another device."""
    monkeypatch.setenv("BOARDFARM_MAX_SSH_TERMINALS", "1")
    wan = _SshDevice()
    env.session.runtime.device_manager.devices["wan"] = wan
    with _connect(env) as lan:
        _attached(lan)
        with env.client.websocket_connect(
            "/devices/wan/ssh-terminal", headers={"X-Boardfarm-User": "bob"}
        ) as other:
            assert _attached(other)["state"] == "attached"
        assert wan.names == ["wan.term1"]


def test_ineligible_closes_4404(env: _Env) -> None:
    """A device that cannot offer ssh terminals closes with 4404."""
    env.device._config["connection_type"] = "telnet"
    with _connect(env) as ws:
        assert _closes_with(ws) == 4404


def test_login_failure_closes_4404_scrubbed(env: _Env) -> None:
    """A failed login closes with 4404 and a message without the password."""
    env.device.fail = DeviceConnectionError("boom password=hunter2")
    with _connect(env) as ws:
        assert _status(ws)["state"] == "busy"
        message = _receive(ws)
        assert message["type"] == "websocket.close"
        assert message["code"] == 4404
        assert "hunter2" not in message["reason"]
        assert "boom" in message["reason"]


def test_output_logged_under_term_name(env: _Env) -> None:
    """The extra console logs as ``pexpect.lan.term1`` under device ``lan``."""
    with _connect(env) as ws:
        _attached(ws)
        ws.send_bytes(b"ping\n")
        _read_until(ws, "ping")
        assert _wait(
            lambda: any(
                e.device == "lan" and "ping" in e.line
                for e in env.session.buffer.read(cursor=0, limit=1000)[0]
            ),
        )


def test_release_closes_ssh_terminals_4410(env: _Env) -> None:
    """Releasing the session closes ssh terminals with 4410."""
    with _connect(env) as ws:
        _attached(ws)
        assert env.client.delete("/session").status_code in (200, 202, 204)
        assert _closes_with(ws) == 4410
    assert env.device.opened[0].closed is True


def test_open_extra_console_uses_device_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The extra console is built from the device's settings; ``_console`` stays."""
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    spawn = type("Spawn", (), {"login_to_server": lambda _s, **_k: None})()
    spawn.logins = []  # type: ignore[attr-defined]

    def fake_factory(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return spawn

    monkeypatch.setattr(linux_device, "connection_factory", fake_factory)
    device = object.__new__(LinuxDevice)
    sentinel = object()
    device._console = sentinel  # type: ignore[assignment]
    device._config = {
        "connection_type": "ssh_connection",
        "ipaddr": "10.0.0.5",
        "port": "2222",
        "username": "bob",
        "password": "pw",
    }
    device._cmdline_args = type("A", (), {"save_console_logs": ""})()
    device._shell_prompt = ["PROMPT"]
    result = device.open_extra_console("lan.term1")
    assert result is spawn
    assert device._console is sentinel
    ((args, kwargs),) = calls
    assert args == ("ssh_connection", "lan.term1")
    assert kwargs["username"] == "bob"
    assert kwargs["password"] == "pw"  # noqa: S105
    assert kwargs["ip_addr"] == "10.0.0.5"
    assert kwargs["port"] == "2222"
    assert kwargs["shell_prompt"] == ["PROMPT"]
    assert kwargs["env"]["TERM"] == "xterm"


def test_ssh_connection_without_env_keeps_dumb_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without ``env``, SSHConnection spawns with the default ``TERM=dumb``."""
    seen: list[Any] = []

    def fake_spawn(_self: Any, *_a: Any, **kwargs: Any) -> None:
        seen.append(kwargs.get("env"))
        raise _Stop

    monkeypatch.setattr(pexpect.spawn, "__init__", fake_spawn)
    with pytest.raises(_Stop):
        SSHConnection("n", "10.0.0.1", "u", ["p"])
    assert seen[0]["TERM"] == "dumb"
    seen.clear()
    with pytest.raises(_Stop):
        SSHConnection("n", "10.0.0.1", "u", ["p"], env={"TERM": "xterm"})
    assert seen[0] == {"TERM": "xterm"}


class _Stop(Exception):
    """Raised by the patched spawn to stop after capturing its env."""


def test_limit_zero_disables_ssh_terminals(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BOARDFARM_MAX_SSH_TERMINALS=0 refuses every ssh terminal (4404)."""
    monkeypatch.setenv("BOARDFARM_MAX_SSH_TERMINALS", "0")
    assert not ssh_terminal_eligible(env.device)
    with _connect(env) as ws:
        assert _closes_with(ws) == 4404
    assert env.device.names == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 5),
        ("", 5),
        ("0", 0),
        ("3", 3),
        (" 7 ", 7),
        ("-1", 5),
        ("lots", 5),
        ("2.5", 5),
    ],
)
def test_max_ssh_terminals_parsing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raw: str | None,
    expected: int,
) -> None:
    """An int >= 0 is used as is; anything else falls back to 5 with a warning."""
    if raw is None:
        monkeypatch.delenv("BOARDFARM_MAX_SSH_TERMINALS", raising=False)
    else:
        monkeypatch.setenv("BOARDFARM_MAX_SSH_TERMINALS", raw)
    with caplog.at_level("WARNING", logger="boardfarm3.api.terminal"):
        assert max_ssh_terminals() == expected
    invalid = raw is not None and raw.strip() != "" and expected == 5
    assert ("invalid BOARDFARM_MAX_SSH_TERMINALS" in caplog.text) == invalid
