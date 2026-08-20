"""Corpse and bundle reaping."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.reaper import reap_once
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore

_DAY = 86_400


async def _dead_session(launcher: FakeLauncher, registry: SessionRegistry) -> None:
    info = await launcher.start("s-1", "board", "img", "prplos")
    registry.add(info)
    await launcher.stop("s-1", remove=False)
    registry.mark_dead("s-1", ended_at=0.0)


@pytest.mark.asyncio
async def test_purges_a_corpse_past_the_ttl(tmp_path: Path) -> None:
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    await _dead_session(launcher, registry)
    result = await reap_once(
        launcher=launcher,
        registry=registry,
        store=store,
        now=2 * _DAY,
    )
    assert result["containers"] == 1
    assert await launcher.list_sessions() == []
    assert registry.get("s-1") is None


@pytest.mark.asyncio
async def test_keeps_a_corpse_within_the_ttl(tmp_path: Path) -> None:
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    await _dead_session(launcher, registry)
    result = await reap_once(
        launcher=launcher,
        registry=registry,
        store=store,
        now=60.0,
    )
    assert result["containers"] == 0
    assert registry.get("s-1") is not None


@pytest.mark.asyncio
async def test_never_touches_a_live_session(tmp_path: Path) -> None:
    """The reaper must be incapable of reaching a running agent."""
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    info = await launcher.start("s-live", "board", "img", "prplos")
    registry.add(info)
    await reap_once(
        launcher=launcher,
        registry=registry,
        store=store,
        now=10 * _DAY,
    )
    assert registry.get("s-live") is not None
    assert [s.session_id for s in await launcher.list_sessions()] == ["s-live"]


@pytest.mark.asyncio
async def test_size_cap_evicts_oldest_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDFARM_BUNDLE_MAX_BYTES", "40")
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    store.write_meta("s-old", {"ended_at": 1.0})
    store.write_bundle("s-old", [b"x" * 30])
    store.write_meta("s-new", {"ended_at": 100.0})
    store.write_bundle("s-new", [b"y" * 30])
    await reap_once(launcher=launcher, registry=registry, store=store, now=200.0)
    assert not store.has_bundle("s-old")
    assert store.has_bundle("s-new")
