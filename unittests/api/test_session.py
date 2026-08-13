"""Unit tests for the boardfarm API session state machine."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

import pytest

from boardfarm3.api.runtime import RuntimeOptions
from boardfarm3.api.session import Session, SessionState
from boardfarm3.exceptions import DeviceBootFailure, EnvConfigError


class FakeRuntime:
    """RuntimeContext stand-in that records calls instead of touching devices."""

    def __init__(
        self,
        *,
        resolve_error: Exception | None = None,
        boot_error: Exception | None = None,
    ) -> None:
        """Initialise the fake.

        :param resolve_error: raise this from resolve()
        :type resolve_error: Exception | None
        :param boot_error: raise this from boot_blocking()
        :type boot_error: Exception | None
        """
        self.resolve_error = resolve_error
        self.boot_error = boot_error
        self.calls: list[str] = []
        self.config = None
        self.device_manager = None

    def refresh_cmdline_args(self) -> None:
        """Record that options were re-materialised."""
        self.calls.append("refresh_cmdline_args")

    def resolve(self, payload: dict[str, Any]) -> object:  # noqa: ARG002
        """Record the call and optionally fail.

        The configured error is an exception instance, so darglint2 cannot
        infer its type from ``raise self.resolve_error``.

        # noqa: DAR401
        # noqa: DAR402

        :param payload: opaque payload
        :type payload: dict[str, Any]
        :raises Exception: when configured to fail
        :return: a placeholder config
        :rtype: object
        """
        self.calls.append("resolve")
        if self.resolve_error:
            raise self.resolve_error
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Record the call.

        :return: a placeholder device manager
        :rtype: object
        """
        self.calls.append("register_devices")
        self.device_manager = object()
        return self.device_manager

    def boot_blocking(self) -> None:
        """Record the call and optionally fail.

        The configured error is an exception instance, so darglint2 cannot
        infer its type from ``raise self.boot_error``.

        # noqa: DAR401
        # noqa: DAR402

        :raises Exception: when configured to fail
        """
        self.calls.append("boot")
        if self.boot_error:
            raise self.boot_error

    def release(self, deployment_status: dict[str, Any]) -> None:
        """Record the call.

        :param deployment_status: deployment outcome
        :type deployment_status: dict[str, Any]
        """
        self.calls.append(f"release:{deployment_status['status']}")


@pytest.fixture(name="make_session")
def make_session_fixture() -> Callable[..., Session]:
    """Build sessions and guarantee each one's console capture is uninstalled.

    Two ``ConsoleCapture`` instances step on each other through the global
    ``pexpect`` logger: whichever installs second snapshots the
    already-modified ``propagate`` value, so its own later ``uninstall()``
    restores the wrong value. Every session built through this factory is
    tracked and torn down here -- ``uninstall()`` and ``queue.shutdown()``
    are both safe to call twice, so this is harmless even for a test that
    already released its own session -- which keeps a leftover session from
    outliving its test with capture still installed.

    :yield: factory that builds and tracks a session
    :rtype: Callable[..., Session]
    """
    created: list[Session] = []

    def factory(runtime: FakeRuntime | None = None) -> Session:
        built = Session(
            session_id="s-test",
            options=RuntimeOptions(board_name="board-1"),
            runtime=runtime if runtime is not None else FakeRuntime(),
        )
        created.append(built)
        return built

    yield factory
    for built in created:
        built.queue.shutdown()
        built.capture.uninstall()


@pytest.fixture(name="session")
def session_fixture(make_session: Callable[..., Session]) -> Session:
    """Build a session backed by a fake runtime.

    :param make_session: factory that builds and tracks a session
    :type make_session: Callable[..., Session]
    :return: session
    :rtype: Session
    """
    return make_session()


@pytest.mark.asyncio
async def test_new_session_starts_created(session: Session) -> None:
    """A fresh session has not been configured yet.

    :param session: session under test
    :type session: Session
    """
    assert session.state is SessionState.CREATED


@pytest.mark.asyncio
async def test_configure_moves_to_configured(session: Session) -> None:
    """Configuring resolves the payload and registers devices.

    :param session: session under test
    :type session: Session
    """
    await session.configure({"inventory": {}, "env": {}})
    assert session.state is SessionState.CONFIGURED
    assert session.runtime.calls == [
        "refresh_cmdline_args",
        "resolve",
        "register_devices",
    ]


@pytest.mark.asyncio
async def test_configure_applies_option_overrides(session: Session) -> None:
    """Options in the config body reach RuntimeOptions before devices are built.

    :param session: session under test
    :type session: Session
    """
    await session.configure(
        {"inventory": {}, "env": {}},
        {"legacy": True, "save_console_logs": "/var/log/bf"},
    )
    assert session.options.legacy is True
    assert session.options.save_console_logs == "/var/log/bf"
    assert session.runtime.calls[0] == "refresh_cmdline_args"


@pytest.mark.asyncio
async def test_status_reports_stuck_when_a_job_overruns(session: Session) -> None:
    """A job running past the watchdog threshold is reported as stuck.

    :param session: session under test
    :type session: Session
    """
    session.stuck_after = 0.05
    await session.configure({"inventory": {}, "env": {}})
    await session.queue.submit(lambda: time.sleep(0.4), mode="async")  # noqa: ASYNC251
    await asyncio.sleep(0.2)
    assert session.status()["state"] == SessionState.STUCK.value
    assert session.is_stuck() is True


@pytest.mark.asyncio
async def test_configure_failure_raises_and_stays_created(
    make_session: Callable[..., Session],
) -> None:
    """A bad payload fails fast without moving the session forward.

    :param make_session: factory that builds and tracks a session
    :type make_session: Callable[..., Session]
    """
    session = make_session(
        runtime=FakeRuntime(resolve_error=EnvConfigError("bad inventory")),
    )
    with pytest.raises(EnvConfigError):
        await session.configure({"inventory": {}, "env": {}})
    assert session.state is SessionState.CREATED


@pytest.mark.asyncio
async def test_boot_moves_to_ready(session: Session) -> None:
    """A successful boot leaves the session ready.

    :param session: session under test
    :type session: Session
    """
    await session.configure({"inventory": {}, "env": {}})
    await session.boot()
    assert session.state is SessionState.READY
    assert "boot" in session.runtime.calls


@pytest.mark.asyncio
async def test_boot_failure_records_error_and_keeps_session(
    make_session: Callable[..., Session],
) -> None:
    """A failed boot moves to FAILED and records the exception.

    :param make_session: factory that builds and tracks a session
    :type make_session: Callable[..., Session]
    """
    session = make_session(
        runtime=FakeRuntime(boot_error=DeviceBootFailure("cpe did not come up")),
    )
    await session.configure({"inventory": {}, "env": {}})
    await session.boot()
    assert session.state is SessionState.FAILED
    assert session.status()["error"]["error"] == "DeviceBootFailure"
    assert session.status()["error"]["message"] == "cpe did not come up"


@pytest.mark.asyncio
async def test_boot_before_configure_is_rejected(session: Session) -> None:
    """Booting an unconfigured session is a programming error.

    :param session: session under test
    :type session: Session
    """
    with pytest.raises(RuntimeError, match="configure"):
        await session.boot()


@pytest.mark.asyncio
async def test_release_reports_status_and_stops_capture(session: Session) -> None:
    """Releasing runs boardfarm teardown with the final deployment status.

    :param session: session under test
    :type session: Session
    """
    await session.configure({"inventory": {}, "env": {}})
    await session.boot()
    await session.release()
    assert "release:success" in session.runtime.calls


@pytest.mark.asyncio
async def test_status_reports_lifecycle_fields(session: Session) -> None:
    """Status carries the fields the control plane surfaces.

    :param session: session under test
    :type session: Session
    """
    status = session.status()
    assert status["session_id"] == "s-test"
    assert status["board_name"] == "board-1"
    assert status["state"] == "created"
    assert status["created_at"] > 0
    assert status["last_activity"] > 0
