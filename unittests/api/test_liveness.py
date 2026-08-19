"""Liveness reporting: quiet is evidence, never a verdict."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

from boardfarm3.api.session import Session, SessionState

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.asyncio
async def test_idle_job_reports_quiet_without_changing_state(
    make_session: Callable[..., Session],
) -> None:
    """A silent job must not destroy the real lifecycle state.

    :param make_session: session factory fixture
    :type make_session: Callable[..., Session]
    """
    session = make_session(quiet_after=0.1)
    await session.configure({"inventory": {}, "env": {}})
    await session.queue.submit(lambda: time.sleep(0.5), mode="async")  # noqa: ASYNC251
    await asyncio.sleep(0.3)
    status = session.status()
    assert status["state"] == SessionState.CONFIGURED.value
    assert status["liveness"]["quiet"] is True
    assert status["liveness"]["running_for"] > 0
    session.queue.shutdown()


@pytest.mark.asyncio
async def test_chatty_job_is_never_quiet(
    make_session: Callable[..., Session],
) -> None:
    """A slow-but-chatty job is healthy and must not be flagged.

    :param make_session: session factory fixture
    :type make_session: Callable[..., Session]
    """
    session = make_session(quiet_after=0.1)
    await session.configure({"inventory": {}, "env": {}})

    def chatty() -> None:
        for _ in range(10):
            session.buffer.append(
                stream="console",
                device="board",
                job_id=None,
                line="working",
            )
            time.sleep(0.05)

    await session.queue.submit(chatty, mode="async")
    await asyncio.sleep(0.3)
    assert session.status()["liveness"]["quiet"] is False
    session.queue.shutdown()


@pytest.mark.asyncio
async def test_quiet_clears_when_output_resumes(
    make_session: Callable[..., Session],
) -> None:
    """Quiet is reversible — one more log line clears it.

    :param make_session: session factory fixture
    :type make_session: Callable[..., Session]
    """
    session = make_session(quiet_after=0.1)
    await session.configure({"inventory": {}, "env": {}})
    await session.queue.submit(lambda: time.sleep(0.6), mode="async")  # noqa: ASYNC251
    await asyncio.sleep(0.3)
    assert session.status()["liveness"]["quiet"] is True
    session.buffer.append(
        stream="console",
        device="board",
        job_id=None,
        line="alive again",
    )
    liveness = session.status()["liveness"]
    assert liveness["quiet"] is False
    assert liveness["last_line"] == "alive again"
    session.queue.shutdown()


def test_liveness_with_no_running_job(
    make_session: Callable[..., Session],
) -> None:
    """An idle session is not quiet — there is nothing to be quiet about.

    :param make_session: session factory fixture
    :type make_session: Callable[..., Session]
    """
    session = make_session(quiet_after=0.1)
    liveness = session.liveness()
    assert liveness["quiet"] is False
    assert liveness["running_for"] is None
    assert liveness["idle_for"] is None


def test_stuck_state_is_gone() -> None:
    """STUCK overwrote the real state and must not come back."""
    assert not hasattr(SessionState, "STUCK")
    assert not hasattr(Session, "is_stuck")
