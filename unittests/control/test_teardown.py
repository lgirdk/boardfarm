"""The teardown matrix: what is pulled, retained, and released."""

from __future__ import annotations

import asyncio
import io
import tarfile
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


@pytest.mark.asyncio
@respx.mock
async def test_lease_is_released_even_when_launcher_stop_fails(
    tmp_path: Path,
) -> None:
    """launcher.stop() itself raising must not strand a board.

    Steps 1 (archive) and 2 (graceful release) were already best-effort;
    step 3 (``launcher.stop()``) was not, so a Docker daemon ``APIError``
    there used to skip lease release entirely.
    """
    launcher, info, registry, lease, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"BUNDLE"),
    )
    respx.delete(f"{info.agent_url}/session").mock(
        return_value=httpx.Response(200, json={}),
    )

    async def _boom(*_args: object, **_kwargs: object) -> None:
        msg = "docker daemon unreachable"
        raise RuntimeError(msg)

    launcher.stop = _boom  # type: ignore[method-assign]

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
    assert lease.held_by("board") is None
    # stop() failed, so the container's real state is unknown -- the corpse
    # must stay visible rather than vanish from the registry.
    listed = registry.get("s-1")
    assert listed is not None
    assert listed.state == "dead"


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


@pytest.mark.asyncio
@respx.mock
async def test_archive_bundle_uses_the_session_artifact_root_not_the_default(
    tmp_path: Path,
) -> None:
    """A per-session BOARDFARM_ARTIFACT_DIR override must reach capture_files.

    Before the fix, tier-3 capture hardcoded "/var/log/boardfarm" regardless
    of any per-session override, so a session configured with a different
    artifact root silently retrieved nothing useful on a hard-crash fallback.
    It must also be scoped to *this* session's own subdirectory, never the
    shared root, so no other session's files can be swept in.
    """
    launcher = FakeLauncher()
    info = await launcher.start(
        "s-1",
        "board",
        "img",
        "prplos",
        agent_env={"BOARDFARM_ARTIFACT_DIR": "/custom/artifacts"},
    )
    assert info.artifact_dir == "/custom/artifacts"
    store = DiagnosticsStore(root=tmp_path)
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
            artifact_dir=info.artifact_dir,
        )
    assert source == "launcher"
    bundle_bytes = store.bundle_path("s-1").read_bytes()
    with tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz") as archive:
        artifacts_member = archive.extractfile("artifacts.tar")
        assert artifacts_member is not None
        content = artifacts_member.read()
    # FakeLauncher.capture_files() echoes back the path it was handed, so this
    # proves the resolved per-session directory reached the launcher, not the
    # hardcoded default root and not some other session's directory.
    assert b"/custom/artifacts/s-1" in content
