"""Tests for SessionRegistry."""

from __future__ import annotations

import time

import pytest

from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.models import AgentInfo
from boardfarm3_control.registry import SessionRegistry


def _info(sid: str, port: int = 18000, board: str = "board-1") -> AgentInfo:
    return AgentInfo(
        session_id=sid,
        board_name=board,
        runtime_profile="prplos",
        container_id=f"c-{sid}",
        host_port=port,
        created_at=0.0,
        pid=None,
        agent_url=f"http://localhost:{port}",
    )


def test_add_and_get() -> None:
    reg = SessionRegistry()
    info = _info("s-aaa")
    reg.add(info)
    assert reg.get("s-aaa") is info


def test_get_unknown_returns_none() -> None:
    reg = SessionRegistry()
    assert reg.get("s-unknown") is None


def test_remove() -> None:
    reg = SessionRegistry()
    reg.add(_info("s-aaa"))
    reg.remove("s-aaa")
    assert reg.get("s-aaa") is None


def test_remove_unknown_is_noop() -> None:
    reg = SessionRegistry()
    reg.remove("s-nonexistent")  # must not raise


def test_list_page_returns_slice_and_total() -> None:
    reg = SessionRegistry()
    for i in range(5):
        reg.add(_info(f"s-{i:03}", port=18000 + i, board=f"board-{i}"))
    page, total = reg.list_page(offset=1, limit=2)
    assert total == 5
    assert len(page) == 2


def test_list_page_offset_beyond_total() -> None:
    reg = SessionRegistry()
    reg.add(_info("s-aaa"))
    page, total = reg.list_page(offset=10, limit=20)
    assert total == 1
    assert page == []


def test_agent_info_agent_url_field() -> None:
    reg = SessionRegistry()
    reg.add(_info("s-aaa", port=19999))
    info = reg.get("s-aaa")
    assert info is not None
    assert info.agent_url == "http://localhost:19999"


def test_get_unknown_session_returns_none() -> None:
    reg = SessionRegistry()
    assert reg.get("s-unknown") is None


def test_touch_and_last_activity() -> None:
    reg = SessionRegistry()
    reg.add(_info("s-aaa"))
    before = time.time()
    reg.touch("s-aaa")
    after = time.time()
    la = reg.last_activity("s-aaa")
    assert la is not None
    assert before <= la <= after


def test_last_activity_unknown_returns_none() -> None:
    reg = SessionRegistry()
    assert reg.last_activity("s-unknown") is None


@pytest.mark.asyncio
async def test_rebuild_from_launcher() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-aaa", "board-1", "img", "prplos")
    await launcher.start("s-bbb", "board-2", "img", "prplos")
    reg = SessionRegistry()
    await reg.rebuild(launcher)
    assert reg.get("s-aaa") is not None
    assert reg.get("s-bbb") is not None
    info = reg.get("s-aaa")
    assert info is not None
    assert info.agent_url == "http://localhost:18000"
