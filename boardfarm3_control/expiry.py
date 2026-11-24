"""Ending live sessions that nobody is using any more."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING

import httpx

from boardfarm3.api import SESSION_HEADER
from boardfarm3_control.teardown import teardown_session

if TYPE_CHECKING:
    from collections.abc import Callable

    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.lease import BoardLease
    from boardfarm3_control.models import AgentInfo
    from boardfarm3_control.registry import SessionRegistry
    from boardfarm3_control.store import DiagnosticsStore

_log = logging.getLogger(__name__)

IDLE_TTL_ENV = "BOARDFARM_SESSION_IDLE_TTL"
MAX_TTL_ENV = "BOARDFARM_SESSION_MAX_TTL"
INTERVAL_ENV = "BOARDFARM_EXPIRY_INTERVAL"
DEFAULT_IDLE_TTL = 4 * 3600.0
DEFAULT_MAX_TTL = 0.0  # 0 disables the hard limit
DEFAULT_INTERVAL = 60.0
_PROBE_TIMEOUT = 5.0


def _env_seconds(name: str, default: float) -> float:
    return float(os.environ.get(name, "").strip() or default)


async def _running_a_job(info: AgentInfo, http: httpx.AsyncClient) -> bool:
    """Ask the agent whether a job (a long test, an image flash) is running.

    :param info: the session's agent info
    :type info: AgentInfo
    :param http: client for the agent
    :type http: httpx.AsyncClient
    :return: True when the agent reports a running job
    :rtype: bool
    """
    try:
        response = await http.get(
            f"{info.agent_url}/session",
            headers={SESSION_HEADER: info.session_id},
            timeout=_PROBE_TIMEOUT,
        )
        liveness = response.json().get("liveness") or {}
    except (httpx.HTTPError, ValueError, AttributeError):
        return False
    return liveness.get("running_for") is not None


async def _expiry_reason(
    info: AgentInfo,
    registry: SessionRegistry,
    http: httpx.AsyncClient,
    now: float,
    ttls: tuple[float, float],
) -> str | None:
    """Tell why a live session should expire now, or None to keep it.

    Touches the session when its activity is unknown or a job is running, so
    either starts a fresh idle window.

    :param info: the session's agent info
    :type info: AgentInfo
    :param registry: session registry
    :type registry: SessionRegistry
    :param http: client for the session's agent
    :type http: httpx.AsyncClient
    :param now: current time
    :type now: float
    :param ttls: ``(idle_ttl, max_ttl)`` in seconds; 0 disables either
    :type ttls: tuple[float, float]
    :return: the reason to expire it, or None
    :rtype: str | None
    """
    idle_ttl, max_ttl = ttls
    if max_ttl > 0 and now - info.created_at > max_ttl:
        return f"older than the {max_ttl:.0f} s maximum lifetime"
    if idle_ttl <= 0:
        return None
    last = registry.last_activity(info.session_id)
    if last is None or (now - last > idle_ttl and await _running_a_job(info, http)):
        registry.touch(info.session_id)
        return None
    if now - last <= idle_ttl:
        return None
    return f"idle for more than {idle_ttl:.0f} s"


async def expire_once(  # noqa: PLR0913
    *,
    registry: SessionRegistry,
    launcher: Launcher,
    lease: BoardLease,
    store: DiagnosticsStore,
    inflight: set[str],
    http_for: Callable[[AgentInfo], httpx.AsyncClient],
    now: float,
    idle_ttl: float,
    max_ttl: float,
) -> list[str]:
    """Tear down every live session past its idle or maximum lifetime.

    Idle time runs from the last call a client made through control. A job
    still running on the agent counts as activity; the maximum lifetime does
    not care. A session whose last activity is unknown (control restarted)
    starts a fresh idle window instead of being expired on the spot.

    :param registry: session registry
    :type registry: SessionRegistry
    :param launcher: launcher owning the agents
    :type launcher: Launcher
    :param lease: board leases
    :type lease: BoardLease
    :param store: diagnostics store the teardown archives into
    :type store: DiagnosticsStore
    :param inflight: sessions with a create or teardown in progress
    :type inflight: set[str]
    :param http_for: returns the HTTP client for a session's agent
    :type http_for: Callable[[AgentInfo], httpx.AsyncClient]
    :param now: current time
    :type now: float
    :param idle_ttl: seconds without activity before expiry; 0 disables
    :type idle_ttl: float
    :param max_ttl: seconds after creation before expiry; 0 disables
    :type max_ttl: float
    :return: the expired session ids
    :rtype: list[str]
    """
    expired: list[str] = []
    for snapshot in registry.sessions():
        session_id = snapshot.session_id
        if snapshot.state != "live" or session_id in inflight:
            continue
        reason = await _expiry_reason(
            snapshot, registry, http_for(snapshot), now, (idle_ttl, max_ttl)
        )
        if reason is None:
            continue
        # The snapshot is stale by now: the job probe and earlier teardowns
        # awaited, and a DELETE (or a retain) may have handled this session.
        info = registry.get(session_id)
        if info is None or info.state != "live" or session_id in inflight:
            continue
        _log.warning(
            "expiring session %s (board %s): %s", session_id, info.board_name, reason
        )
        inflight.add(session_id)
        try:
            await teardown_session(
                session_id=session_id,
                info=info,
                launcher=launcher,
                registry=registry,
                lease=lease,
                store=store,
                http=http_for(info),
                retain=False,
            )
        except Exception:  # noqa: BLE001
            _log.exception("could not expire session %s", session_id)
            continue
        finally:
            inflight.discard(session_id)
        expired.append(session_id)
    return expired


async def run_expiry(  # noqa: PLR0913
    *,
    registry: SessionRegistry,
    launcher: Launcher,
    lease: BoardLease,
    store: DiagnosticsStore,
    inflight: set[str],
    http_for: Callable[[AgentInfo], httpx.AsyncClient],
) -> None:
    """Run :func:`expire_once` on a fixed interval until cancelled.

    :param registry: session registry
    :type registry: SessionRegistry
    :param launcher: launcher owning the agents
    :type launcher: Launcher
    :param lease: board leases
    :type lease: BoardLease
    :param store: diagnostics store the teardown archives into
    :type store: DiagnosticsStore
    :param inflight: sessions with a create or teardown in progress
    :type inflight: set[str]
    :param http_for: returns the HTTP client for a session's agent
    :type http_for: Callable[[AgentInfo], httpx.AsyncClient]
    """
    interval = _env_seconds(INTERVAL_ENV, DEFAULT_INTERVAL)
    while True:
        await asyncio.sleep(interval)
        try:
            await expire_once(
                registry=registry,
                launcher=launcher,
                lease=lease,
                store=store,
                inflight=inflight,
                http_for=http_for,
                now=time.time(),
                idle_ttl=_env_seconds(IDLE_TTL_ENV, DEFAULT_IDLE_TTL),
                max_ttl=_env_seconds(MAX_TTL_ENV, DEFAULT_MAX_TTL),
            )
        except Exception:  # noqa: BLE001
            _log.exception("session expiry pass failed")
