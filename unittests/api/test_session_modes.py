"""Sessions in a non-interactive mode never build devices."""

from __future__ import annotations

import logging
import tempfile
from typing import TYPE_CHECKING

import pytest

from boardfarm3.api.modes import ModeRequestError
from boardfarm3.api.session import Session, SessionConflict, SessionState

from ._fake_mode import FakeMode
from .conftest import FakeRuntime

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_MODES = {"fake": FakeMode}


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    FakeMode.instances.clear()


def _private_dirs(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "tmp").glob("bf-run-*"))


async def test_a_mode_session_never_builds_devices(
    make_session: Callable[..., Session],
) -> None:
    runtime = FakeRuntime()
    session = make_session(runtime=runtime, modes=_MODES)
    await session.configure({"inventory": {}}, {}, mode="fake", run={})
    assert session.state is SessionState.RUNNING
    assert session.mode == "fake"
    assert "resolve" not in runtime.calls
    assert "register_devices" not in runtime.calls


async def test_an_unknown_mode_is_refused(make_session: Callable[..., Session]) -> None:
    session = make_session(modes=_MODES)
    with pytest.raises(ModeRequestError, match="unknown mode 'robot'"):
        await session.configure({}, {}, mode="robot", run={})
    assert session.state is SessionState.CREATED
    assert session.error is not None
    assert session.error["error"] == "ModeRequestError"


async def test_a_run_in_interact_mode_is_refused(
    make_session: Callable[..., Session],
) -> None:
    session = make_session(modes=_MODES)
    with pytest.raises(ModeRequestError, match="run applies only"):
        await session.configure({}, {}, mode="interact", run={})
    assert session.state is SessionState.CREATED


async def test_a_mode_without_a_run_is_refused(
    make_session: Callable[..., Session],
) -> None:
    session = make_session(modes=_MODES)
    with pytest.raises(ModeRequestError, match="needs a run"):
        await session.configure({}, {}, mode="fake", run=None)


async def test_a_bad_run_leaves_the_session_retryable(
    make_session: Callable[..., Session], tmp_path: Path
) -> None:
    session = make_session(modes=_MODES)
    with pytest.raises(ModeRequestError, match="bad run"):
        await session.configure({}, {}, mode="fake", run={"bad": True})
    assert session.state is SessionState.CREATED
    assert session.mode == "interact"
    assert _private_dirs(tmp_path) == []
    await session.configure({}, {}, mode="fake", run={})
    assert session.state is SessionState.RUNNING


async def test_a_mode_that_cannot_start_fails_the_session(
    make_session: Callable[..., Session], tmp_path: Path
) -> None:
    session = make_session(modes=_MODES)
    with pytest.raises(OSError, match="cannot spawn"):
        await session.configure({}, {}, mode="fake", run={"explode": True})
    assert session.state is SessionState.FAILED
    assert session.run is None
    assert session.mode == "fake"
    assert session.error is not None
    assert session.error["message"] == "cannot spawn"
    assert _private_dirs(tmp_path) == []


async def test_the_end_of_the_run_finishes_the_session(
    make_session: Callable[..., Session], tmp_path: Path
) -> None:
    session = make_session(modes=_MODES)
    await session.configure({}, {}, mode="fake", run={})
    assert len(_private_dirs(tmp_path)) == 1
    FakeMode.instances[-1].end()
    assert session.state is SessionState.FINISHED
    assert _private_dirs(tmp_path) == []


async def test_liveness_follows_the_run(make_session: Callable[..., Session]) -> None:
    session = make_session(modes=_MODES)
    await session.configure({}, {}, mode="fake", run={})
    assert session.liveness()["running_for"] is not None
    FakeMode.instances[-1].end()
    assert session.liveness()["running_for"] is None


async def test_status_reports_the_mode_and_the_run(
    make_session: Callable[..., Session],
) -> None:
    session = make_session(modes=_MODES)
    assert session.status()["mode"] == "interact"
    assert session.status()["run"] is None
    await session.configure({}, {}, mode="fake", run={})
    assert session.status()["mode"] == "fake"
    assert session.status()["run"] == {"state": "running", "fake": True}


async def test_release_cancels_a_running_run(
    make_session: Callable[..., Session],
) -> None:
    session = make_session(modes=_MODES)
    await session.configure({}, {}, mode="fake", run={})
    await session.release()
    assert FakeMode.instances[-1].cancel_calls == 1
    assert session.state is SessionState.FINISHED


async def test_mode_output_is_attributed_to_the_run(
    make_session: Callable[..., Session],
) -> None:
    session = make_session(modes=_MODES)
    await session.configure({}, {}, mode="fake", run={})
    FakeMode.instances[-1].context.emit("hello")
    events, _ = session.buffer.read(stream="fake")
    assert [(event.line, event.job_id) for event in events] == [("hello", "run-s-test")]


async def test_a_mode_session_configures_once(
    make_session: Callable[..., Session],
) -> None:
    session = make_session(modes=_MODES)
    await session.configure({}, {}, mode="fake", run={})
    with pytest.raises(SessionConflict):
        await session.configure({}, {}, mode="fake", run={})


class _UncancellableMode(FakeMode):
    """A run whose cancel fails."""

    async def cancel(self) -> bool:
        self.cancel_calls += 1
        msg = "cancel failed"
        raise RuntimeError(msg)


class _CrashingValidateMode(FakeMode):
    def validate(self) -> None:
        msg = "validate broke"
        raise RuntimeError(msg)


class _CrashingInitMode(FakeMode):
    def __init__(self, *_args: object) -> None:
        msg = "constructor broke"
        raise RuntimeError(msg)


async def test_release_goes_on_when_a_run_cannot_be_cancelled(
    make_session: Callable[..., Session], caplog: pytest.LogCaptureFixture
) -> None:
    runtime = FakeRuntime()
    session = make_session(runtime=runtime, modes={"stuck": _UncancellableMode})
    await session.configure({}, {}, mode="stuck", run={})
    with caplog.at_level(logging.ERROR, logger="boardfarm3.api.session"):
        await session.release()
    assert FakeMode.instances[-1].cancel_calls == 1
    assert "release:failed" in runtime.calls
    assert session.capture not in logging.getLogger("boardfarm3").handlers
    with pytest.raises(RuntimeError, match="shutdown"):
        await session.queue.submit(lambda: None, mode="sync")
    errors = [
        record
        for record in caplog.records
        if record.name == "boardfarm3.api.session" and record.levelno == logging.ERROR
    ]
    assert len(errors) == 1
    assert "stuck" in errors[0].getMessage()
    assert errors[0].exc_info is not None
    assert str(errors[0].exc_info[1]) == "cancel failed"


@pytest.mark.parametrize(
    "crashing", [_CrashingValidateMode, _CrashingInitMode], ids=["validate", "init"]
)
async def test_a_mode_that_crashes_before_starting_leaves_nothing_behind(
    make_session: Callable[..., Session], tmp_path: Path, crashing: type[FakeMode]
) -> None:
    session = make_session(modes={"crash": crashing, "fake": FakeMode})
    with pytest.raises(RuntimeError, match="broke"):
        await session.configure({}, {}, mode="crash", run={})
    assert _private_dirs(tmp_path) == []
    assert session._private_dir is None
    assert session.state is SessionState.CREATED
    assert session.mode == "interact"
    assert session.error is not None
    assert session.error["error"] == "RuntimeError"
    await session.configure({}, {}, mode="fake", run={})
    assert session.state is SessionState.RUNNING
    assert len(_private_dirs(tmp_path)) == 1
