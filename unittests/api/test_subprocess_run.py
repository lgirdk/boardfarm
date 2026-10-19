"""SubprocessRun: one supervised process per run."""

from __future__ import annotations

import argparse
import asyncio
import errno
import gc
import io
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

import pytest

from boardfarm3.api import modes
from boardfarm3.api.modes import CANCEL_GRACE_ENV, Command, ModeContext, SubprocessRun

if TYPE_CHECKING:
    from collections.abc import Callable


class _ScriptRun(SubprocessRun):
    stream_name = "script"

    def __init__(
        self, context: ModeContext, script: str, argv: list[str] | None = None
    ) -> None:
        super().__init__(context)
        self._script = script
        self._argv = argv

    def validate(self) -> None:
        return None

    def command(self) -> Command:
        argv = self._argv or [sys.executable, "-c", self._script]
        return Command(
            argv=argv, env=dict(os.environ), cwd=self.context.run_dir, display=argv[:2]
        )

    def summary(self, exit_code: int | None, *, cancelled: bool) -> dict[str, Any]:
        return {"cancelled": cancelled, "seen_exit": exit_code}


def _context(tmp_path: Path, lines: list[str], finished: list[bool]) -> ModeContext:
    return ModeContext(
        session_id="s-test",
        board_name="board",
        payload={},
        options={},
        run={},
        run_dir=tmp_path / "run",
        private_dir=tmp_path / "private",
        boardfarm_parser=argparse.ArgumentParser(add_help=False),
        emit=lines.append,
        finished=lambda: finished.append(True),
    )


async def _until(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            msg = "condition not reached"
            raise AssertionError(msg)
        await asyncio.sleep(0.02)


def _alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except FileNotFoundError:
        return False
    return stat.split(") ", 1)[1].split()[0] != "Z"


def _open_fds() -> int:
    return len(list(Path("/proc/self/fd").iterdir()))


class _FullDisk(io.BytesIO):
    """A log file on a full disk: every write fails."""

    def write(self, _chunk: bytes, /) -> int:
        msg = "No space left on device"
        raise OSError(errno.ENOSPC, msg)


def _full_device_log() -> BinaryIO:
    """Open /dev/full, where every write fails with ENOSPC."""
    return Path("/dev/full").open("ab")


class _BrokenSummaryRun(_ScriptRun):
    def summary(self, exit_code: int | None, *, cancelled: bool) -> dict[str, Any]:
        if exit_code is not None:
            msg = "summary broke"
            raise RuntimeError(msg)
        return super().summary(exit_code, cancelled=cancelled)


async def test_output_reaches_the_stream_and_the_log(tmp_path: Path) -> None:
    lines: list[str] = []
    finished: list[bool] = []
    run = _ScriptRun(
        _context(tmp_path, lines, finished),
        "print('one'); print('two'); raise SystemExit(3)",
    )
    await run.start()
    await asyncio.wait_for(run.wait(), 10)
    assert lines == ["one", "two"]
    assert (tmp_path / "run" / "script.log").read_text() == "one\ntwo\n"
    status = run.status()
    assert status["state"] == "finished"
    assert status["exit_code"] == 3
    assert status["seen_exit"] == 3
    assert status["command"] == [sys.executable, "-c"]
    assert finished == [True]
    saved = json.loads((tmp_path / "run" / "run.json").read_text())
    assert saved["exit_code"] == 3


async def test_running_since_is_set_only_while_running(tmp_path: Path) -> None:
    run = _ScriptRun(_context(tmp_path, [], []), "import time; time.sleep(30)")
    await run.start()
    assert run.running_since() is not None
    assert run.status()["state"] == "running"
    assert run.status()["seen_exit"] is None
    assert await run.cancel() is True
    assert run.running_since() is None


async def test_cancel_sends_ctrl_c_first(tmp_path: Path) -> None:
    script = (
        "import signal, sys, time\n"
        "def stop(*_):\n"
        "    print('interrupted', flush=True)\n"
        "    sys.exit(2)\n"
        "signal.signal(signal.SIGINT, stop)\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    lines: list[str] = []
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    await run.start()
    await _until(lambda: "ready" in lines)
    assert await run.cancel() is True
    assert "interrupted" in lines
    assert run.status()["exit_code"] == 2
    assert run.status()["cancelled"] is True


async def test_a_process_ignoring_ctrl_c_is_terminated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CANCEL_GRACE_ENV, "0.2")
    script = (
        "import signal, time\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    lines: list[str] = []
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    await run.start()
    await _until(lambda: "ready" in lines)
    started = time.monotonic()
    await run.cancel()
    assert run.status()["exit_code"] == -signal.SIGTERM
    assert time.monotonic() - started < 5


async def test_a_process_ignoring_ctrl_c_and_terminate_is_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CANCEL_GRACE_ENV, "0.2")
    monkeypatch.setattr(modes, "_TERM_GRACE", 0.5)
    script = (
        "import signal, time\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('ready', flush=True)\n"
        "time.sleep(60)\n"
    )
    lines: list[str] = []
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    await run.start()
    try:
        await _until(lambda: "ready" in lines)
        started = time.monotonic()
        await run.cancel()
        assert run.status()["exit_code"] == -signal.SIGKILL
        assert run.status()["cancelled"] is True
        assert time.monotonic() - started < 5
    finally:
        if run.running_since() is not None:
            # The escalation failed; do not leave the child running.
            os.killpg(run._process.pid, signal.SIGKILL)
            await asyncio.wait_for(run.wait(), 10)


async def test_cancel_reaches_the_whole_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CANCEL_GRACE_ENV, "0.2")
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    lines: list[str] = []
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    await run.start()
    await _until(lambda: bool(lines))
    child = int(lines[0])
    await run.cancel()
    await _until(lambda: not _alive(child))


async def test_output_without_newlines_is_streamed_in_pieces(tmp_path: Path) -> None:
    lines: list[str] = []
    script = "import sys\nsys.stdout.write('x' * 200_000)\nsys.stdout.flush()\n"
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    await run.start()
    await asyncio.wait_for(run.wait(), 10)
    assert len(lines) >= 2
    assert sum(len(line) for line in lines) == 200_000


async def test_cancelling_twice_sends_one_ctrl_c(tmp_path: Path) -> None:
    script = (
        "import signal, sys, time\n"
        "count = 0\n"
        "def stop(*_):\n"
        "    global count\n"
        "    count += 1\n"
        "    print(f'sigint {count}', flush=True)\n"
        "    time.sleep(0.5)\n"
        "    sys.exit(2)\n"
        "signal.signal(signal.SIGINT, stop)\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    lines: list[str] = []
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    await run.start()
    await _until(lambda: "ready" in lines)
    first = asyncio.create_task(run.cancel())
    await _until(lambda: "sigint 1" in lines)
    assert await run.cancel() is True
    assert await first is True
    assert [line for line in lines if line.startswith("sigint")] == ["sigint 1"]


async def test_cancel_after_the_end_does_nothing(tmp_path: Path) -> None:
    run = _ScriptRun(_context(tmp_path, [], []), "pass")
    await run.start()
    await asyncio.wait_for(run.wait(), 10)
    assert await run.cancel() is False


async def test_a_command_that_cannot_start_raises(tmp_path: Path) -> None:
    run = _ScriptRun(
        _context(tmp_path, [], []), "", argv=[str(tmp_path / "missing-binary")]
    )
    with pytest.raises(FileNotFoundError):
        await run.start()
    assert run.running_since() is None


async def test_a_daemon_holding_the_pipe_does_not_keep_the_run_going(
    tmp_path: Path,
) -> None:
    # A descendant in its own session escapes the process group and keeps
    # stdout open; the run must still end soon after its own process exits.
    script = (
        "import subprocess, sys\n"
        "daemon = subprocess.Popen([sys.executable, '-c',"
        " 'import os, time; os.setsid(); time.sleep(30)'])\n"
        "print(daemon.pid, flush=True)\n"
    )
    lines: list[str] = []
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    await run.start()
    try:
        await asyncio.wait_for(run.wait(), 10)
        assert run.status()["exit_code"] == 0
    finally:
        if lines:
            os.kill(int(lines[0]), signal.SIGKILL)


async def test_a_failing_log_does_not_stop_the_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(CANCEL_GRACE_ENV, "0.2")
    (tmp_path / "run").mkdir()
    # The output must overflow the pipe, or the old code would not block the child.
    script = (
        "for i in range(20000):\n    print(f'line {i:04d}', 'x' * 64, flush=True)\n"
    )
    lines: list[str] = []
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    monkeypatch.setattr(run, "_open_log", _FullDisk)
    with caplog.at_level(logging.WARNING, logger="boardfarm3.api.modes"):
        await run.start()
        try:
            await asyncio.wait_for(run.wait(), 10)
        finally:
            await run.cancel()
    assert run.status()["exit_code"] == 0
    assert len(lines) == 20000
    assert lines[-1] == f"line 19999 {'x' * 64}"
    warnings = [
        record
        for record in caplog.records
        if record.name == "boardfarm3.api.modes" and record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1


async def test_a_failing_summary_still_finishes_the_run(tmp_path: Path) -> None:
    finished: list[bool] = []
    run = _BrokenSummaryRun(_context(tmp_path, [], finished), "pass")
    await run.start()
    await asyncio.wait_for(run.wait(), 10)
    assert finished == [True]
    assert not (tmp_path / "run" / "run.json").exists()


async def test_a_spawn_failure_leaks_nothing(tmp_path: Path) -> None:
    run = _ScriptRun(
        _context(tmp_path, [], []), "", argv=[sys.executable, "-c", "\x00"]
    )
    gc.collect()
    open_fds = _open_fds()
    with pytest.raises(ValueError, match="embedded null byte"):
        await run.start()
    assert run._log_file is None
    assert _open_fds() == open_fds


async def test_a_log_on_a_full_device_still_finishes_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "run").mkdir()
    script = "for i in range(3):\n    print(f'line {i}', flush=True)\n"
    lines: list[str] = []
    finished: list[bool] = []
    run = _ScriptRun(_context(tmp_path, lines, finished), script)
    monkeypatch.setattr(run, "_open_log", _full_device_log)
    with caplog.at_level(logging.WARNING, logger="boardfarm3.api.modes"):
        await run.start()
        await asyncio.wait_for(run.wait(), 5)
    assert finished == [True]
    assert run.status()["state"] == "finished"
    assert run.status()["exit_code"] == 0
    assert lines == ["line 0", "line 1", "line 2"]
    assert (tmp_path / "run" / "run.json").exists()
    warnings = [
        record
        for record in caplog.records
        if record.name == "boardfarm3.api.modes" and record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1


async def test_a_malformed_cancel_grace_still_cancels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(CANCEL_GRACE_ENV, "abc")
    script = (
        "import signal, sys, time\n"
        "def stop(*_):\n"
        "    print('interrupted', flush=True)\n"
        "    sys.exit(2)\n"
        "signal.signal(signal.SIGINT, stop)\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    lines: list[str] = []
    run = _ScriptRun(_context(tmp_path, lines, []), script)
    await run.start()
    try:
        await _until(lambda: "ready" in lines)
        with caplog.at_level(logging.WARNING, logger="boardfarm3.api.modes"):
            assert await run.cancel() is True
    finally:
        if run.running_since() is not None:
            # The cancel failed; do not leave the child running.
            os.killpg(run._process.pid, signal.SIGKILL)
            await asyncio.wait_for(run.wait(), 10)
    assert "interrupted" in lines
    assert run.status()["exit_code"] == 2
    warnings = [
        record
        for record in caplog.records
        if record.name == "boardfarm3.api.modes" and record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert CANCEL_GRACE_ENV in warnings[0].getMessage()


@pytest.mark.parametrize(
    "raw",
    ["abc", "", "-1", "nan", "inf"],
    ids=["text", "empty", "negative", "nan", "infinite"],
)
def test_an_unusable_cancel_grace_falls_back_to_the_default(
    raw: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(CANCEL_GRACE_ENV, raw)
    with caplog.at_level(logging.WARNING, logger="boardfarm3.api.modes"):
        grace = modes._cancel_grace()
    assert grace == modes._DEFAULT_CANCEL_GRACE
    warnings = [
        record
        for record in caplog.records
        if record.name == "boardfarm3.api.modes" and record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert CANCEL_GRACE_ENV in warnings[0].getMessage()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, modes._DEFAULT_CANCEL_GRACE), ("0", 0.0), ("0.2", 0.2)],
    ids=["unset", "zero", "fraction"],
)
def test_a_usable_cancel_grace_is_used_without_a_warning(
    raw: str | None,
    expected: float,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    if raw is None:
        monkeypatch.delenv(CANCEL_GRACE_ENV, raising=False)
    else:
        monkeypatch.setenv(CANCEL_GRACE_ENV, raw)
    with caplog.at_level(logging.WARNING, logger="boardfarm3.api.modes"):
        assert modes._cancel_grace() == expected
    assert [r for r in caplog.records if r.name == "boardfarm3.api.modes"] == []
