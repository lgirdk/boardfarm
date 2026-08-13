"""Tests for BoardLease."""

from __future__ import annotations

import asyncio

import pytest

from boardfarm3_control.lease import BoardLease
from boardfarm3_control.models import AgentInfo


def _info(board: str, sid: str) -> AgentInfo:
    return AgentInfo(
        session_id=sid,
        board_name=board,
        runtime_profile="prplos",
        container_id=f"c-{sid}",
        host_port=18000,
        created_at=0.0,
    )


@pytest.mark.asyncio
async def test_acquire_fresh_board_returns_true() -> None:
    lease = BoardLease()
    assert await lease.acquire("board-1", "s-aaa") is True


@pytest.mark.asyncio
async def test_acquire_held_board_returns_false() -> None:
    lease = BoardLease()
    await lease.acquire("board-1", "s-aaa")
    assert await lease.acquire("board-1", "s-bbb") is False


@pytest.mark.asyncio
async def test_held_by_returns_session_id() -> None:
    lease = BoardLease()
    await lease.acquire("board-1", "s-aaa")
    assert lease.held_by("board-1") == "s-aaa"


@pytest.mark.asyncio
async def test_release_allows_reacquire() -> None:
    lease = BoardLease()
    await lease.acquire("board-1", "s-aaa")
    await lease.release("s-aaa")
    assert await lease.acquire("board-1", "s-bbb") is True


@pytest.mark.asyncio
async def test_release_unknown_session_is_noop() -> None:
    lease = BoardLease()
    await lease.release("s-nonexistent")  # must not raise


@pytest.mark.asyncio
async def test_rebuild_from_populates_leases() -> None:
    lease = BoardLease()
    sessions = [_info("board-1", "s-aaa"), _info("board-2", "s-bbb")]
    await lease.rebuild_from(sessions)
    assert lease.held_by("board-1") == "s-aaa"
    assert lease.held_by("board-2") == "s-bbb"
    # A board from the list cannot be acquired by a new session
    assert await lease.acquire("board-1", "s-ccc") is False
