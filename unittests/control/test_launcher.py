"""Tests for Launcher implementations (FakeLauncher only — no Docker daemon)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from boardfarm3_control.launcher import FakeLauncher, ProcessLauncher
from boardfarm3_control.models import AgentInfo


def test_agent_info_has_pid_and_agent_url() -> None:
    info = AgentInfo(
        session_id="s-aaa",
        board_name="board-1",
        runtime_profile="prplos",
        container_id="c-1",
        host_port=18000,
        created_at=0.0,
        pid=None,
        agent_url="http://localhost:18000",
    )
    assert info.pid is None
    assert info.agent_url == "http://localhost:18000"


@pytest.mark.asyncio
async def test_fake_launcher_start_returns_agent_info() -> None:
    launcher = FakeLauncher()
    info = await launcher.start("s-abc", "board-1", "agent:latest", "prplos")
    assert info.session_id == "s-abc"
    assert info.board_name == "board-1"
    assert info.runtime_profile == "prplos"
    assert info.container_id == "fake-s-abc"
    assert info.host_port == 18000  # first allocated port


@pytest.mark.asyncio
async def test_fake_launcher_stop_removes_session() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-abc", "board-1", "agent:latest", "prplos")
    await launcher.stop("s-abc")
    sessions = await launcher.list_sessions()
    assert sessions == []


@pytest.mark.asyncio
async def test_fake_launcher_stop_unknown_session_is_noop() -> None:
    launcher = FakeLauncher()
    await launcher.stop("s-nonexistent")  # must not raise


@pytest.mark.asyncio
async def test_fake_launcher_list_sessions_returns_all() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-aaa", "board-1", "agent:latest", "prplos")
    await launcher.start("s-bbb", "board-2", "agent:latest", "prplos")
    sessions = await launcher.list_sessions()
    sids = {s.session_id for s in sessions}
    assert sids == {"s-aaa", "s-bbb"}


@pytest.mark.asyncio
async def test_fake_launcher_ports_are_unique() -> None:
    launcher = FakeLauncher()
    a = await launcher.start("s-aaa", "board-1", "img", "p")
    b = await launcher.start("s-bbb", "board-2", "img", "p")
    assert a.host_port != b.host_port


@pytest.mark.asyncio
async def test_fake_launcher_start_sets_pid_none_and_agent_url() -> None:
    launcher = FakeLauncher()
    info = await launcher.start("s-abc", "board-1", "agent:latest", "prplos")
    assert info.pid is None
    assert info.agent_url == "http://localhost:18000"


@pytest.mark.asyncio
async def test_fake_launcher_agent_url_increments_with_port() -> None:
    launcher = FakeLauncher()
    a = await launcher.start("s-aaa", "board-1", "img", "p")
    b = await launcher.start("s-bbb", "board-2", "img", "p")
    assert a.agent_url == "http://localhost:18000"
    assert b.agent_url == "http://localhost:18001"


@pytest.mark.asyncio
async def test_process_launcher_start_sets_pid_and_agent_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ProcessLauncher.start() sets pid and agent_url on the returned AgentInfo."""
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    launcher = ProcessLauncher()
    info = await launcher.start("s-proc", "board-1", "ignored", "prplos")
    assert isinstance(info.pid, int)
    assert info.pid > 0
    assert info.agent_url == f"http://localhost:{info.host_port}"
    await launcher.stop("s-proc")


@pytest.mark.asyncio
async def test_process_launcher_start_writes_state_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ProcessLauncher.start() writes the session to the state file."""
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    launcher = ProcessLauncher()
    info = await launcher.start("s-proc", "board-1", "ignored", "prplos")
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert "s-proc" in data
    assert data["s-proc"]["pid"] == info.pid
    await launcher.stop("s-proc")


@pytest.mark.asyncio
async def test_process_launcher_stop_removes_from_state_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ProcessLauncher.stop() removes the session from the state file."""
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    launcher = ProcessLauncher()
    await launcher.start("s-proc", "board-1", "ignored", "prplos")
    await launcher.stop("s-proc")
    data = json.loads(state_file.read_text())
    assert "s-proc" not in data


@pytest.mark.asyncio
async def test_process_launcher_list_sessions_kills_orphaned_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh ProcessLauncher with a state file containing a live PID kills it."""
    import asyncio

    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))

    # Start a real process to use as an orphan target
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(60)",
    )
    orphan_pid = proc.pid

    # Write it into the state file as if a previous control plane left it
    state_file.write_text(
        json.dumps(
            {
                "s-orphan": {
                    "session_id": "s-orphan",
                    "board_name": "board-x",
                    "runtime_profile": "p",
                    "container_id": str(orphan_pid),
                    "host_port": 19999,
                    "created_at": 0.0,
                    "pid": orphan_pid,
                    "agent_url": "http://localhost:19999",
                },
            },
        ),
    )

    # A fresh launcher should kill the orphan when list_sessions() is called
    fresh_launcher = ProcessLauncher()
    sessions = await fresh_launcher.list_sessions()

    assert sessions == []
    # PID should now be dead
    try:
        os.kill(orphan_pid, 0)
        is_dead = False
    except ProcessLookupError:
        is_dead = True
    assert is_dead, f"orphaned PID {orphan_pid} was not killed"


@pytest.mark.asyncio
async def test_process_launcher_list_sessions_missing_state_file_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_sessions() returns [] when state file does not exist."""
    state_file = tmp_path / "nonexistent.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    launcher = ProcessLauncher()
    sessions = await launcher.list_sessions()
    assert sessions == []


@pytest.mark.asyncio
async def test_process_launcher_list_sessions_corrupt_state_file_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_sessions() returns [] when state file is not valid JSON."""
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    state_file.write_text("not valid json {{{")
    launcher = ProcessLauncher()
    sessions = await launcher.list_sessions()
    assert sessions == []


@pytest.mark.asyncio
async def test_fake_launcher_retains_on_stop_without_remove() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-1", "board", "img", "prplos")
    await launcher.stop("s-1", remove=False)
    sessions = await launcher.list_sessions()
    assert [s.session_id for s in sessions] == ["s-1"]
    assert sessions[0].state == "dead"


@pytest.mark.asyncio
async def test_fake_launcher_purge_removes_the_record() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-1", "board", "img", "prplos")
    await launcher.stop("s-1", remove=False)
    await launcher.purge("s-1")
    assert await launcher.list_sessions() == []


@pytest.mark.asyncio
async def test_fake_launcher_stop_with_remove_purges() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-1", "board", "img", "prplos")
    await launcher.stop("s-1")
    assert await launcher.list_sessions() == []


@pytest.mark.asyncio
async def test_fake_launcher_capture_returns_bytes() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-1", "board", "img", "prplos")
    assert isinstance(await launcher.capture_logs("s-1"), bytes)
    assert isinstance(await launcher.capture_files("s-1", "/var/log"), bytes)


@pytest.mark.asyncio
async def test_capture_on_unknown_session_returns_empty() -> None:
    launcher = FakeLauncher()
    assert await launcher.capture_logs("nope") == b""
    assert await launcher.capture_files("nope", "/var/log") == b""
