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
async def test_never_touches_a_live_session_even_with_a_stale_ended_at(
    tmp_path: Path,
) -> None:
    """The ``state`` guard is load-bearing on its own, not via ``ended_at``.

    Every real code path that sets ``ended_at`` also flips ``state`` to
    ``dead`` at the same time (``mark_dead`` / ``stop(remove=False)``), so a
    *live* entry always has ``ended_at is None`` in practice. That means the
    other live-session test can't tell whether the reaper skipped it because
    of ``state`` or because ``ended_at`` was ``None``. This test builds a
    synthetic (currently unreachable in production) registry entry that is
    ``state == "live"`` but carries a very old ``ended_at``, to prove the
    ``state`` check itself -- not a side effect of ``ended_at`` -- is what
    keeps the reaper off a live session.
    """
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    info = await launcher.start("s-live-stale", "board", "img", "prplos")
    registry.add(info.model_copy(update={"ended_at": 0.0}))
    await reap_once(
        launcher=launcher,
        registry=registry,
        store=store,
        now=10 * _DAY,
    )
    live = registry.get("s-live-stale")
    assert live is not None
    assert live.state == "live"
    assert [s.session_id for s in await launcher.list_sessions()] == ["s-live-stale"]


@pytest.mark.asyncio
async def test_bundle_with_no_ended_at_is_not_reaped(tmp_path: Path) -> None:
    """A missing timestamp must never be the trigger for a destructive action.

    Before the fix, a missing ``ended_at`` defaulted to 0.0, making the
    bundle look infinitely old and evicting it on the very first pass.
    """
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    store.write_bundle("s-no-meta", [b"BUNDLE"])  # no write_meta() call at all
    result = await reap_once(
        launcher=launcher,
        registry=registry,
        store=store,
        now=100 * _DAY,
    )
    assert result["bundles"] == 0
    assert store.has_bundle("s-no-meta")


@pytest.mark.asyncio
async def test_bundle_with_meta_missing_ended_at_key_is_not_reaped(
    tmp_path: Path,
) -> None:
    """Same as above, but meta.json exists without an ``ended_at`` key."""
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    store.write_meta("s-partial-meta", {"session_id": "s-partial-meta"})
    store.write_bundle("s-partial-meta", [b"BUNDLE"])
    result = await reap_once(
        launcher=launcher,
        registry=registry,
        store=store,
        now=100 * _DAY,
    )
    assert result["bundles"] == 0
    assert store.has_bundle("s-partial-meta")


@pytest.mark.asyncio
async def test_live_sessions_bundle_is_never_reaped_regardless_of_meta(
    tmp_path: Path,
) -> None:
    """A registry-live session must never lose its store entry to the TTL sweep.

    Even a stale/ancient ``ended_at`` in meta.json must not matter once the
    registry says the session is still ``live`` -- the registry is the
    authority on liveness, not whatever a store's meta.json happens to say.
    """
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    info = await launcher.start("s-live", "board", "img", "prplos")
    registry.add(info)
    store.write_meta("s-live", {"ended_at": 1.0})  # ancient, if it mattered
    store.write_bundle("s-live", [b"BUNDLE"])
    result = await reap_once(
        launcher=launcher,
        registry=registry,
        store=store,
        now=100 * _DAY,
    )
    assert result["bundles"] == 0
    assert store.has_bundle("s-live")


@pytest.mark.asyncio
async def test_size_cap_evicts_oldest_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 60, not 40: the cap must be compared against real on-disk bytes
    # (bundle + meta.json), not bundle bytes alone -- each session here is
    # ~51-53 bytes on disk once its meta.json is counted, so a cap of 40
    # would force evicting both to get under it. 60 sits between the total
    # (104) and a single remaining session's real footprint (53), so the
    # test still exercises "evict oldest, stop once under cap".
    monkeypatch.setenv("BOARDFARM_BUNDLE_MAX_BYTES", "60")
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    store.write_meta("s-old", {"ended_at": 1.0})
    store.write_bundle("s-old", [b"x" * 30])
    store.write_meta("s-new", {"ended_at": 100.0})
    store.write_bundle("s-new", [b"y" * 30])
    await reap_once(launcher=launcher, registry=registry, store=store, now=200.0)
    assert not store.has_bundle("s-old")
    assert store.has_bundle("s-new")


@pytest.mark.asyncio
async def test_size_cap_uses_real_store_bytes_not_bundle_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cap must be judged against real disk usage, not bundle bytes alone.

    Three 15-byte bundles sum to 45 bytes -- under the 60-byte cap -- so a
    reaper that measured only bundle bytes would wrongly decide nothing
    needs evicting. Real on-disk usage (bundles + each session's
    ``meta.json``) is well over the cap and must trigger oldest-first
    eviction until the store is back under it.
    """
    monkeypatch.setenv("BOARDFARM_BUNDLE_MAX_BYTES", "60")
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    for session_id, ended_at in (
        ("s-a", 1000.0),
        ("s-b", 2000.0),
        ("s-c", 3000.0),
    ):
        store.write_meta(session_id, {"ended_at": ended_at})
        store.write_bundle(session_id, [b"x" * 15])

    bundle_only_total = 3 * 15
    assert bundle_only_total <= 60  # bundle-only accounting says: do nothing

    await reap_once(launcher=launcher, registry=registry, store=store, now=4000.0)

    assert store.total_bytes() <= 60
    assert not store.has_bundle("s-a")
    assert not store.has_bundle("s-b")
    assert store.has_bundle("s-c")
