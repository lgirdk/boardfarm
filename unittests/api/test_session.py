"""Unit tests for the boardfarm API session state machine."""

from __future__ import annotations

from typing import Callable

import pytest

from boardfarm3.api.session import Session, SessionState
from boardfarm3.exceptions import DeviceBootFailure, EnvConfigError

from .conftest import FakeRuntime


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
async def test_empty_save_console_logs_override_keeps_the_default(
    session: Session,
) -> None:
    """An empty override must not disable always-on console logging.

    :param session: session under test
    :type session: Session
    """
    session.options.save_console_logs = "/var/log/boardfarm/s-test"
    await session.configure({"inventory": {}, "env": {}}, {"save_console_logs": ""})
    assert session.options.save_console_logs == "/var/log/boardfarm/s-test"


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
    assert status["board_name"] == "board"
    assert status["state"] == "created"
    assert status["created_at"] > 0
    assert status["last_activity"] > 0
    assert status["boot_job_id"] is None


@pytest.mark.asyncio
async def test_status_boot_job_id_is_none_before_boot(session: Session) -> None:
    """boot_job_id is absent from status until boot is submitted.

    :param session: session under test
    :type session: Session
    """
    assert session.status()["boot_job_id"] is None


@pytest.mark.asyncio
async def test_status_boot_job_id_is_set_after_boot(session: Session) -> None:
    """boot_job_id in status points to the execution queue job for the boot.

    :param session: session under test
    :type session: Session
    """
    await session.configure({"inventory": {}, "env": {}})
    await session.boot()
    boot_job_id = session.status()["boot_job_id"]
    assert boot_job_id is not None
    assert boot_job_id.startswith("j-")
    # The job must be reachable in the queue.
    assert session.queue.get(boot_job_id) is not None
