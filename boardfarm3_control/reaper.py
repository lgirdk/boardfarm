"""Background purge of stopped containers and aged diagnostics bundles.

This module operates only on containers that have *already* stopped. It never
calls ``Launcher.stop()`` and can therefore not terminate a live session.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.registry import SessionRegistry
    from boardfarm3_control.store import DiagnosticsStore

_log = logging.getLogger(__name__)

_CORPSE_TTL = "BOARDFARM_CORPSE_TTL"
_BUNDLE_TTL = "BOARDFARM_BUNDLE_TTL"
_MAX_BYTES = "BOARDFARM_BUNDLE_MAX_BYTES"
_INTERVAL = "BOARDFARM_REAP_INTERVAL"


async def _reap_corpses(
    *,
    launcher: Launcher,
    registry: SessionRegistry,
    now: float,
    corpse_ttl: float,
) -> int:
    """Purge dead containers past the corpse TTL.

    :param launcher: launcher used to purge stopped containers
    :type launcher: Launcher
    :param registry: session registry
    :type registry: SessionRegistry
    :param now: current time, injected for testability
    :type now: float
    :param corpse_ttl: seconds a dead session may remain before purge
    :type corpse_ttl: float
    :return: number of containers purged
    :rtype: int
    """
    containers = 0
    page, _ = registry.list_page(0, 10_000)
    for info in page:
        if info.state != "dead" or info.ended_at is None:
            continue
        age = now - info.ended_at
        if age <= corpse_ttl:
            continue
        await launcher.purge(info.session_id)
        registry.remove(info.session_id)
        containers += 1
        _log.info(
            "reaped container for %s (age %.0fs)",
            info.session_id,
            age,
        )
    return containers


def _reap_aged_bundles(
    *,
    store: DiagnosticsStore,
    now: float,
    bundle_ttl: float,
) -> tuple[int, int, list[tuple[float, str, int]]]:
    """Delete bundles past the bundle TTL.

    :param store: diagnostics store
    :type store: DiagnosticsStore
    :param now: current time, injected for testability
    :type now: float
    :param bundle_ttl: seconds a bundle may remain before deletion
    :type bundle_ttl: float
    :return: (bundles deleted, bytes reclaimed, remaining (ended_at, id, size))
    :rtype: tuple[int, int, list[tuple[float, str, int]]]
    """
    bundles = 0
    reclaimed = 0
    remaining: list[tuple[float, str, int]] = []
    for session_id in store.list_sessions():
        meta = store.read_meta(session_id) or {}
        ended_at = float(meta.get("ended_at") or 0.0)
        size = (
            store.bundle_path(session_id).stat().st_size
            if store.has_bundle(session_id)
            else 0
        )
        if now - ended_at > bundle_ttl:
            store.delete(session_id)
            bundles += 1
            reclaimed += size
            _log.info("reaped bundle for %s (%d bytes)", session_id, size)
            continue
        remaining.append((ended_at, session_id, size))
    return bundles, reclaimed, remaining


def _evict_over_cap(
    *,
    store: DiagnosticsStore,
    aged: list[tuple[float, str, int]],
    max_bytes: int,
) -> tuple[int, int]:
    """Evict bundles oldest-first until the store is back under the cap.

    The running total is the sum of the surviving bundle sizes rather than
    a fresh ``store.total_bytes()`` call, so the decrement on each eviction
    stays exactly consistent with the threshold check (no drift from
    on-disk metadata that isn't tracked per-bundle).

    :param store: diagnostics store
    :type store: DiagnosticsStore
    :param aged: candidate bundles as (ended_at, session_id, size)
    :type aged: list[tuple[float, str, int]]
    :param max_bytes: byte cap for the store
    :type max_bytes: int
    :return: (bundles evicted, bytes reclaimed)
    :rtype: tuple[int, int]
    """
    bundles = 0
    reclaimed = 0
    total = sum(size for _, _, size in aged)
    for _, session_id, size in sorted(aged):
        if total <= max_bytes:
            break
        store.delete(session_id)
        total -= size
        bundles += 1
        reclaimed += size
        _log.info(
            "evicted bundle for %s to stay under the %d byte cap",
            session_id,
            max_bytes,
        )
    return bundles, reclaimed


async def reap_once(
    *,
    launcher: Launcher,
    registry: SessionRegistry,
    store: DiagnosticsStore,
    now: float,
) -> dict[str, int]:
    """Run one reaping pass.

    Purges dead containers past ``BOARDFARM_CORPSE_TTL``, deletes archived
    bundles past ``BOARDFARM_BUNDLE_TTL``, and evicts bundles oldest-first
    when the store exceeds ``BOARDFARM_BUNDLE_MAX_BYTES``. Only ever calls
    ``launcher.purge()`` on entries already ``state == "dead"`` and never
    calls ``launcher.stop()``, so it cannot reach a live session.

    :param launcher: launcher used to purge stopped containers
    :type launcher: Launcher
    :param registry: session registry
    :type registry: SessionRegistry
    :param store: diagnostics store
    :type store: DiagnosticsStore
    :param now: current time, injected for testability
    :type now: float
    :return: counts of purged containers, deleted bundles, and bytes reclaimed
    :rtype: dict[str, int]
    """
    corpse_ttl = float(os.environ.get(_CORPSE_TTL, "86400"))
    bundle_ttl = float(os.environ.get(_BUNDLE_TTL, "604800"))
    max_bytes = int(os.environ.get(_MAX_BYTES, str(20 * 1024**3)))

    containers = await _reap_corpses(
        launcher=launcher,
        registry=registry,
        now=now,
        corpse_ttl=corpse_ttl,
    )
    bundles, reclaimed, aged = _reap_aged_bundles(
        store=store,
        now=now,
        bundle_ttl=bundle_ttl,
    )
    evicted, evicted_bytes = _evict_over_cap(
        store=store,
        aged=aged,
        max_bytes=max_bytes,
    )
    bundles += evicted
    reclaimed += evicted_bytes

    return {"containers": containers, "bundles": bundles, "bytes": reclaimed}


async def run_reaper(
    *,
    launcher: Launcher,
    registry: SessionRegistry,
    store: DiagnosticsStore,
) -> None:
    """Run :func:`reap_once` on a fixed interval until cancelled.

    :param launcher: launcher used to purge stopped containers
    :type launcher: Launcher
    :param registry: session registry
    :type registry: SessionRegistry
    :param store: diagnostics store
    :type store: DiagnosticsStore
    """
    interval = float(os.environ.get(_INTERVAL, "900"))
    while True:
        await asyncio.sleep(interval)
        try:
            await reap_once(
                launcher=launcher,
                registry=registry,
                store=store,
                now=time.time(),
            )
        except Exception:  # noqa: BLE001
            _log.exception("reaper pass failed")
