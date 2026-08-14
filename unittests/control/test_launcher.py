"""Tests for Launcher implementations (FakeLauncher only — no Docker daemon)."""

from __future__ import annotations

import pytest

from boardfarm3_control.launcher import FakeLauncher
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
