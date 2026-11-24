"""Nothing used to end a live session: a forgotten one held its board forever.

Idle time is measured from the last call a client made through control; a
job still running on the agent (a long test) counts as activity. A hard
maximum lifetime, when set, applies regardless.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from typing import TYPE_CHECKING

import httpx
import pytest
import respx
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from boardfarm3_control.app import create_app
from boardfarm3_control.expiry import expire_once
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore
from boardfarm3_control.teardown import teardown_session

if TYPE_CHECKING:
    from pathlib import Path

_HEALTH = re.compile(r"http://localhost:\d+/health")
_CONFIG = re.compile(r"http://localhost:\d+/session/config")
_BOOT = re.compile(r"http://localhost:\d+/session/boot")
_STATUS = re.compile(r"http://localhost:\d+/session$")
_BUNDLE = re.compile(r"http://localhost:\d+/diagnostics/bundle")
_PROFILES = {"prplos": "boardfarm3-agent:latest"}
_BODY = {"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
_HOUR = 3600.0


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))


def _status(running_for: float | None) -> httpx.Response:
    return httpx.Response(
        200,
        json={"state": "ready", "liveness": {"running_for": running_for}},
    )


async def _world() -> tuple[FakeLauncher, SessionRegistry, BoardLease, str]:
    launcher = FakeLauncher()
    registry = SessionRegistry()
    lease = BoardLease()
    info = await launcher.start("s-1", "b1", "img", "prplos")
    registry.add(info)
    await lease.acquire("b1", "s-1")
    return launcher, registry, lease, info.session_id


async def _expire(  # noqa: PLR0913
    launcher: FakeLauncher,
    registry: SessionRegistry,
    lease: BoardLease,
    *,
    now: float,
    idle_ttl: float = 4 * _HOUR,
    max_ttl: float = 0.0,
) -> list[str]:
    async with httpx.AsyncClient() as http:
        return await expire_once(
            registry=registry,
            launcher=launcher,
            lease=lease,
            store=DiagnosticsStore(),
            inflight=set(),
            http_for=lambda _info: http,
            now=now,
            idle_ttl=idle_ttl,
            max_ttl=max_ttl,
        )


@respx.mock
async def test_idle_session_is_torn_down_and_its_board_freed() -> None:
    respx.get(_STATUS).mock(return_value=_status(None))
    respx.get(_BUNDLE).mock(return_value=httpx.Response(200, content=b"tar"))
    respx.delete(_STATUS).mock(return_value=httpx.Response(200, json={}))
    launcher, registry, lease, session_id = await _world()
    registry.touch(session_id)

    expired = await _expire(launcher, registry, lease, now=time.time() + 5 * _HOUR)

    assert expired == [session_id]
    assert lease.held_by("b1") is None
    assert registry.get(session_id) is None
    assert await launcher.list_sessions() == []


@respx.mock
async def test_a_running_job_is_activity() -> None:
    respx.get(_STATUS).mock(return_value=_status(1800.0))
    launcher, registry, lease, session_id = await _world()
    registry.touch(session_id)

    expired = await _expire(launcher, registry, lease, now=time.time() + 5 * _HOUR)

    assert expired == []
    assert lease.held_by("b1") == session_id


@respx.mock
async def test_recent_activity_keeps_the_session() -> None:
    launcher, registry, lease, session_id = await _world()
    registry.touch(session_id)

    expired = await _expire(launcher, registry, lease, now=time.time() + _HOUR)

    assert expired == []
    assert lease.held_by("b1") == session_id


@respx.mock
async def test_max_lifetime_applies_even_to_a_busy_session() -> None:
    respx.get(_STATUS).mock(return_value=_status(1800.0))
    respx.get(_BUNDLE).mock(return_value=httpx.Response(200, content=b"tar"))
    respx.delete(_STATUS).mock(return_value=httpx.Response(200, json={}))
    launcher, registry, lease, session_id = await _world()
    registry.touch(session_id)

    expired = await _expire(
        launcher,
        registry,
        lease,
        now=time.time() + 25 * _HOUR,
        idle_ttl=0.0,
        max_ttl=24 * _HOUR,
    )

    assert expired == [session_id]
    assert lease.held_by("b1") is None


@respx.mock
class _SlowStopLauncher(FakeLauncher):
    """Takes a while to stop ``s-slow``, leaving a window during an expiry pass."""

    def __init__(self) -> None:
        super().__init__()
        self.stops: list[tuple[str, bool]] = []

    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        self.stops.append((session_id, remove))
        if session_id == "s-slow":
            await asyncio.sleep(0.3)
        await super().stop(session_id, remove=remove)


@pytest.mark.asyncio
@respx.mock
async def test_a_session_retained_during_the_pass_is_left_alone() -> None:
    """Expiry re-reads the registry: a session retained meanwhile keeps its container."""
    respx.get(re.compile(r".*/session$")).mock(return_value=_status(None))
    respx.delete(re.compile(r".*/session$")).mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get(re.compile(r".*/diagnostics/bundle")).mock(
        return_value=httpx.Response(200, content=b"x")
    )
    launcher = _SlowStopLauncher()
    registry, lease, store = SessionRegistry(), BoardLease(), DiagnosticsStore()
    for session_id, board in (("s-slow", "b-1"), ("s-kept", "b-2")):
        registry.add(await launcher.start(session_id, board, "img", "prplos"))
        await lease.acquire(board, session_id)
        registry._last_activity[session_id] = time.time() - 10 * 3600
    inflight: set[str] = set()
    async with httpx.AsyncClient() as http:
        expiring = asyncio.create_task(
            expire_once(
                registry=registry,
                launcher=launcher,
                lease=lease,
                store=store,
                inflight=inflight,
                http_for=lambda _info: http,
                now=time.time(),
                idle_ttl=3600,
                max_ttl=0,
            )
        )
        await asyncio.sleep(0.1)  # expiry is busy stopping s-slow
        # Meanwhile: DELETE /sessions/s-kept?retain=true
        inflight.add("s-kept")
        await teardown_session(
            session_id="s-kept",
            info=registry.get("s-kept"),
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=store,
            http=http,
            retain=True,
        )
        inflight.discard("s-kept")
        expired = await expiring
    assert expired == ["s-slow"]
    assert ("s-kept", True) not in launcher.stops
    assert registry.get("s-kept") is not None


async def test_unknown_activity_after_a_restart_starts_a_fresh_idle_window() -> None:
    launcher, registry, lease, session_id = await _world()  # never touched

    expired = await _expire(launcher, registry, lease, now=time.time() + 5 * _HOUR)

    assert expired == []
    assert registry.last_activity(session_id) is not None


# -- what counts as activity -----------------------------------------------------


def _mock_agent() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))


@respx.mock
def test_listing_sessions_is_not_activity() -> None:
    _mock_agent()
    respx.get(_STATUS).mock(
        return_value=httpx.Response(200, json={"state": "ready", "last_activity": 1.0})
    )
    app = create_app(FakeLauncher(), _PROFILES)
    with TestClient(app) as client:
        session_id = client.post("/sessions", json=_BODY).json()["session_id"]
        before = app.state.registry.last_activity(session_id)
        time.sleep(0.01)
        client.get("/sessions")
        assert app.state.registry.last_activity(session_id) == before


class _EchoRequest(BaseModel):
    text: str


_plugin_router = APIRouter()


@_plugin_router.post("/core/use_cases/demo/echo")
async def _echo(body: _EchoRequest) -> dict:  # noqa: ARG001
    return {"result": "unused"}


@respx.mock
def test_a_plugin_route_call_is_activity() -> None:
    _mock_agent()
    respx.post(re.compile(r"http://localhost:\d+/core/use_cases/demo/echo")).mock(
        return_value=httpx.Response(200, json={"result": "hi"})
    )
    app = create_app(FakeLauncher(), _PROFILES, extra_routers=[_plugin_router])
    with TestClient(app) as client:
        session_id = client.post("/sessions", json=_BODY).json()["session_id"]
        before = app.state.registry.last_activity(session_id)
        time.sleep(0.01)
        client.post(
            "/core/use_cases/demo/echo", json={"session_id": session_id, "text": "x"}
        )
        assert app.state.registry.last_activity(session_id) > before


@respx.mock
def test_the_running_control_plane_expires_idle_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDFARM_SESSION_IDLE_TTL", "0.1")
    monkeypatch.setenv("BOARDFARM_EXPIRY_INTERVAL", "0.05")
    _mock_agent()
    respx.get(_STATUS).mock(return_value=_status(None))
    respx.get(_BUNDLE).mock(return_value=httpx.Response(200, content=b"tar"))
    respx.delete(_STATUS).mock(return_value=httpx.Response(200, json={}))
    app = create_app(FakeLauncher(), _PROFILES)
    with TestClient(app) as client:
        session_id = client.post("/sessions", json=_BODY).json()["session_id"]
        for _ in range(100):
            if app.state.registry.get(session_id) is None:
                break
            time.sleep(0.02)
        assert app.state.registry.get(session_id) is None
        assert app.state.lease.held_by("b1") is None


# -- a create abandoned after its container started -----------------------------


@respx.mock
async def test_a_cancelled_create_leaves_no_container_and_no_lease() -> None:
    entered = asyncio.Event()

    async def hang(_request: httpx.Request) -> httpx.Response:
        entered.set()
        await asyncio.sleep(3600)
        return httpx.Response(200)

    respx.get(_HEALTH).mock(side_effect=hang)
    respx.get(_BUNDLE).mock(return_value=httpx.Response(200, content=b"tar"))
    respx.delete(_STATUS).mock(return_value=httpx.Response(200, json={}))
    launcher = FakeLauncher()
    app = create_app(launcher, _PROFILES)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://c"
        ) as client:
            creating = asyncio.create_task(client.post("/sessions", json=_BODY))
            await asyncio.wait_for(entered.wait(), timeout=10)
            creating.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await creating
        for _ in range(200):
            if (
                not await launcher.list_sessions()
                and app.state.lease.held_by("b1") is None
            ):
                break
            await asyncio.sleep(0.01)
        assert await launcher.list_sessions() == []
        assert app.state.lease.held_by("b1") is None
