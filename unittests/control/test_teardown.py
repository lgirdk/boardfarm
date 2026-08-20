"""The teardown matrix: what is pulled, retained, and released."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore
from boardfarm3_control.teardown import archive_bundle, teardown_session

if TYPE_CHECKING:
    from pathlib import Path


async def _prepare(tmp_path: Path) -> tuple:
    launcher = FakeLauncher()
    info = await launcher.start("s-1", "board", "img", "prplos")
    registry = SessionRegistry()
    registry.add(info)
    lease = BoardLease()
    await lease.acquire("board", "s-1")
    return launcher, info, registry, lease, DiagnosticsStore(root=tmp_path)


@pytest.mark.asyncio
@respx.mock
async def test_retain_keeps_the_container_and_marks_dead(tmp_path: Path) -> None:
    launcher, info, registry, lease, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"BUNDLE"),
    )
    respx.delete(f"{info.agent_url}/session").mock(
        return_value=httpx.Response(200, json={}),
    )
    async with httpx.AsyncClient() as http:
        await teardown_session(
            session_id="s-1",
            info=info,
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=store,
            http=http,
            retain=True,
        )
    assert store.bundle_path("s-1").read_bytes() == b"BUNDLE"
    assert [s.session_id for s in await launcher.list_sessions()] == ["s-1"]
    listed = registry.get("s-1")
    assert listed is not None
    assert listed.state == "dead"
    assert lease.held_by("board") is None


@pytest.mark.asyncio
@respx.mock
async def test_clean_delete_removes_container_but_keeps_bundle(
    tmp_path: Path,
) -> None:
    launcher, info, registry, lease, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"BUNDLE"),
    )
    respx.delete(f"{info.agent_url}/session").mock(
        return_value=httpx.Response(200, json={}),
    )
    async with httpx.AsyncClient() as http:
        await teardown_session(
            session_id="s-1",
            info=info,
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=store,
            http=http,
            retain=False,
        )
    assert store.has_bundle("s-1")
    assert await launcher.list_sessions() == []
    assert registry.get("s-1") is None
    assert lease.held_by("board") is None


@pytest.mark.asyncio
@respx.mock
async def test_lease_is_released_even_when_every_step_fails(
    tmp_path: Path,
) -> None:
    """A dead agent must never strand a board."""
    launcher, info, registry, lease, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    respx.delete(f"{info.agent_url}/session").mock(
        side_effect=httpx.ConnectError("down"),
    )
    async with httpx.AsyncClient() as http:
        await teardown_session(
            session_id="s-1",
            info=info,
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=store,
            http=http,
            retain=True,
        )
    assert lease.held_by("board") is None


def test_retain_and_purge_are_mutually_exclusive(
    fake_launcher: FakeLauncher,
    profiles: dict[str, str],
) -> None:
    """Contradictory teardown flags must be rejected, not silently ordered.

    :param fake_launcher: launcher test double
    :type fake_launcher: FakeLauncher
    :param profiles: profile map
    :type profiles: dict[str, str]
    """
    from fastapi.testclient import TestClient

    from boardfarm3_control.app import create_app

    asyncio.run(fake_launcher.start("s-1", "board", "img", "prplos"))
    app = create_app(launcher=fake_launcher, profiles=profiles)
    with TestClient(app) as client:
        response = client.delete("/sessions/s-1?retain=true&purge=true")
    assert response.status_code == 400


@pytest.mark.asyncio
@respx.mock
async def test_archive_falls_back_to_the_launcher(tmp_path: Path) -> None:
    """A crashed agent cannot serve HTTP; the launcher still can."""
    launcher, info, _, _, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    async with httpx.AsyncClient() as http:
        source = await archive_bundle(
            session_id="s-1",
            agent_url=info.agent_url,
            launcher=launcher,
            store=store,
            http=http,
        )
    assert source == "launcher"
    assert store.has_bundle("s-1")
