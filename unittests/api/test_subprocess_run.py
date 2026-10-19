"""SubprocessRun: one supervised process per run."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

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
    first, second = await asyncio.gather(run.cancel(), run.cancel())
    assert (first, second) == (True, True)
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
