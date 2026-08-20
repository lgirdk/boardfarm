"""Tests for Launcher implementations (FakeLauncher only — no Docker daemon)."""

from __future__ import annotations

import io
import json
import os
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

from boardfarm3_control.launcher import DockerLauncher, FakeLauncher, ProcessLauncher
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


@pytest.mark.asyncio
async def test_process_launcher_capture_files_scopes_to_its_own_session(
    tmp_path: Path,
) -> None:
    """capture_files() must never leak another session's directory.

    ProcessLauncher shares its filesystem with the control plane, so if a
    caller ever passed the wrong path -- the shared artifact root instead of
    this session's own subdirectory, say -- this must refuse rather than
    silently archive it.
    """
    launcher = ProcessLauncher()
    own_dir = tmp_path / "s-mine"
    own_dir.mkdir()
    (own_dir / "secret.txt").write_text("mine")
    other_dir = tmp_path / "s-other"
    other_dir.mkdir()
    (other_dir / "secret.txt").write_text("not mine")

    tar_bytes = await launcher.capture_files("s-mine", str(own_dir))
    assert tar_bytes
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as archive:
        names = archive.getnames()
    assert any(name.endswith("secret.txt") for name in names)

    # The final path component does not match the session id -- refused
    # outright, even though the directory is real and readable.
    leaked = await launcher.capture_files("s-mine", str(other_dir))
    assert leaked == b""


@pytest.mark.asyncio
async def test_process_launcher_retains_and_marks_dead_on_stop_without_remove(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stop(remove=False) keeps the record and flips state/ended_at."""
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    launcher = ProcessLauncher()
    await launcher.start("s-proc", "board-1", "ignored", "prplos")
    await launcher.stop("s-proc", remove=False)
    sessions = await launcher.list_sessions()
    assert [s.session_id for s in sessions] == ["s-proc"]
    assert sessions[0].state == "dead"
    assert sessions[0].ended_at is not None


@pytest.mark.asyncio
async def test_process_launcher_start_writes_meta_without_ended_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start() must leave the reaper unable to mistake a live session as dead.

    Before the fix, start() opened process.log but wrote no meta.json at
    all, so the reaper's aged-bundle sweep -- which used to default a
    missing ``ended_at`` to 0.0 -- could rmtree a live agent's own log
    directory on its very first pass.
    """
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    launcher = ProcessLauncher()
    await launcher.start("s-proc", "board-1", "ignored", "prplos")
    meta_path = tmp_path / "sessions" / "s-proc" / "meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["session_id"] == "s-proc"
    assert "ended_at" not in meta
    await launcher.stop("s-proc")


class _FakeContainer:
    """Minimal docker-py container stand-in for DockerLauncher tests."""

    def __init__(
        self,
        *,
        status: str,
        labels: dict[str, str],
        ports: dict[str, list[dict[str, str]]],
        finished_at: str = "",
        container_id: str = "c-1",
    ) -> None:
        self.status = status
        self.labels = labels
        self.ports = ports
        self.id = container_id
        self.attrs: dict[str, Any] = {"State": {"FinishedAt": finished_at}}


class _FakeContainers:
    def __init__(self, containers: list[_FakeContainer]) -> None:
        self._containers = containers

    def list(
        self,
        all: bool = False,  # noqa: A002, ARG002
        filters: dict[str, str] | None = None,  # noqa: ARG002
    ) -> list[_FakeContainer]:
        return self._containers


class _FakeDockerClient:
    def __init__(self, containers: list[_FakeContainer]) -> None:
        self.containers = _FakeContainers(containers)


def _docker_labels(**overrides: str) -> dict[str, str]:
    labels = {
        "boardfarm.session_id": "s-1",
        "boardfarm.board_name": "board",
        "boardfarm.runtime_profile": "prplos",
        "boardfarm.created_at": "0",
    }
    labels.update(overrides)
    return labels


@pytest.mark.asyncio
async def test_docker_launcher_list_sessions_dead_container_has_ended_at() -> None:
    """A stopped container must report state=dead with a real ended_at.

    Before the fix, ended_at always stayed None, so a corpse that survived a
    control plane restart became invisible to the reaper forever.
    """
    container = _FakeContainer(
        status="exited",
        labels=_docker_labels(),
        ports={"8000/tcp": [{"HostPort": "18000"}]},
        finished_at="2024-01-01T12:00:00.123456789Z",
    )
    launcher = DockerLauncher(client=_FakeDockerClient([container]))
    sessions = await launcher.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].state == "dead"
    assert sessions[0].ended_at is not None
    assert sessions[0].ended_at > 0


@pytest.mark.asyncio
async def test_docker_launcher_list_sessions_live_container_has_no_ended_at() -> None:
    container = _FakeContainer(
        status="running",
        labels=_docker_labels(),
        ports={"8000/tcp": [{"HostPort": "18000"}]},
        finished_at="0001-01-01T00:00:00Z",
    )
    launcher = DockerLauncher(client=_FakeDockerClient([container]))
    sessions = await launcher.list_sessions()
    assert sessions[0].state == "live"
    assert sessions[0].ended_at is None


@pytest.mark.asyncio
async def test_docker_launcher_list_sessions_unparseable_finished_at_is_none() -> None:
    container = _FakeContainer(
        status="exited",
        labels=_docker_labels(),
        ports={"8000/tcp": [{"HostPort": "18000"}]},
        finished_at="not-a-timestamp",
    )
    launcher = DockerLauncher(client=_FakeDockerClient([container]))
    sessions = await launcher.list_sessions()
    assert sessions[0].state == "dead"
    assert sessions[0].ended_at is None


@pytest.mark.asyncio
async def test_docker_launcher_start_records_artifact_dir_label() -> None:
    """A per-session BOARDFARM_ARTIFACT_DIR override must survive a restart.

    Docker labels are immutable after creation and are the only thing
    list_sessions() (used to rebuild the registry on restart) can read back.
    """
    container = _FakeContainer(
        status="running",
        labels=_docker_labels(),
        ports={"8000/tcp": [{"HostPort": "18000"}]},
    )

    class _Client:
        def __init__(self) -> None:
            self.containers = self
            self.run_kwargs: dict[str, Any] = {}

        def run(self, image: str, **kwargs: Any) -> _FakeContainer:  # noqa: ARG002
            self.run_kwargs = kwargs
            return container

    client = _Client()
    launcher = DockerLauncher(client=client)
    info = await launcher.start(
        "s-1",
        "board",
        "img",
        "prplos",
        agent_env={"BOARDFARM_ARTIFACT_DIR": "/custom/artifacts"},
    )
    assert info.artifact_dir == "/custom/artifacts"
    assert client.run_kwargs["labels"]["boardfarm.artifact_dir"] == "/custom/artifacts"
