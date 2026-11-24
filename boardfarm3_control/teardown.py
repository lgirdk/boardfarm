"""The single teardown sequence used by DELETE and by every failure unwind."""

from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import tarfile
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx

from boardfarm3.api import SESSION_HEADER
from boardfarm3_control.errors import StopPending

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.lease import BoardLease
    from boardfarm3_control.models import AgentInfo
    from boardfarm3_control.registry import SessionRegistry
    from boardfarm3_control.store import DiagnosticsStore

_log = logging.getLogger(__name__)
# read bounds each wait for a byte, not the whole download: a streaming bundle
# never idles 30 s, and a hung agent (e.g. on a paused host) must not hold a
# DELETE for 5 minutes before the stop is even attempted.
_BUNDLE_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
# Releasing closes every console, after whatever job is running finishes.
_RELEASE_TIMEOUT_ENV = "BOARDFARM_AGENT_RELEASE_TIMEOUT"
_DEFAULT_RELEASE_TIMEOUT = 120.0
_RUN_POLL_INTERVAL = 1.0
# A cancelled run is polled until it ends; this many failed polls in a row (an
# error, or a reply that is not a summary) end the wait early.
_RUN_POLL_FAILURES = 3


def _release_seconds() -> float:
    """Return how long a release, and a run's cancel, may take.

    :return: ``BOARDFARM_AGENT_RELEASE_TIMEOUT`` in seconds, or the default (120)
        when it is unset or not a finite number above 0; a bad value is logged
    :rtype: float
    """
    raw = os.environ.get(_RELEASE_TIMEOUT_ENV)
    if raw is None:
        return _DEFAULT_RELEASE_TIMEOUT
    try:
        seconds = float(raw)
    except ValueError:
        seconds = math.nan
    if math.isfinite(seconds) and seconds > 0:
        return seconds
    _log.warning(
        "ignoring %s=%r, which is not a finite number of seconds above 0; using %s",
        _RELEASE_TIMEOUT_ENV,
        raw,
        _DEFAULT_RELEASE_TIMEOUT,
    )
    return _DEFAULT_RELEASE_TIMEOUT


def _release_timeout() -> httpx.Timeout:
    """Return the timeout for the agent's graceful device release.

    :return: read bound from ``BOARDFARM_AGENT_RELEASE_TIMEOUT``, default 120
    :rtype: httpx.Timeout
    """
    return httpx.Timeout(connect=10.0, read=_release_seconds(), write=30.0, pool=10.0)


# Matches boardfarm3_control.launcher._common._DEFAULT_ARTIFACT_ROOT and
# boardfarm3.api.logs's default. Callers should pass a resolved
# AgentInfo.artifact_dir; this is only the fallback when none is known.
_DEFAULT_ARTIFACT_ROOT = "/var/log/boardfarm"


def _launcher_bundle(logs: bytes, files: bytes) -> bytes:
    """Wrap launcher-captured bytes in the same tar.gz shape as an agent bundle.

    :param logs: container stdout/stderr
    :type logs: bytes
    :param files: tar bytes of the agent artifact directory
    :type files: bytes
    :return: gzip archive
    :rtype: bytes
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in (("docker.log", logs), ("artifacts.tar", files)):
            if not payload:
                continue
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = int(time.time())
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


async def _wait_for_end(
    poll: Callable[[], Awaitable[dict[str, Any] | None]],
    run: dict[str, Any],
    deadline: float,
) -> dict[str, Any]:
    """Poll a cancelled run until it ends, and return its last good summary.

    The wait ends when the run is no longer ``running``, when ``deadline``
    passes, or after ``_RUN_POLL_FAILURES`` failed polls in a row. A failed poll
    does not end the run: the last summary read stays the answer until a later
    poll replaces it.

    :param poll: reads the run once; returns None for a failed read, never raises
    :type poll: Callable[[], Awaitable[dict[str, Any] | None]]
    :param run: the summary read just before the cancel
    :type run: dict[str, Any]
    :param deadline: ``time.monotonic()`` value after which polling stops
    :type deadline: float
    :return: the last summary a read returned; still ``running`` if the wait ran out
    :rtype: dict[str, Any]
    """
    failed = 0
    while (
        run.get("state") == "running"
        and failed < _RUN_POLL_FAILURES
        and time.monotonic() < deadline
    ):
        await asyncio.sleep(_RUN_POLL_INTERVAL)
        polled = await poll()
        if polled is None:
            failed += 1
        else:
            failed, run = 0, polled
    return run


async def _final_run(http: httpx.AsyncClient, info: AgentInfo) -> dict[str, Any] | None:
    """Cancel a session's run if it is still going, and return its final status.

    Cancelling before the bundle is taken means the bundle holds the run's
    final junit.xml and log, not a half-written report. A lookup that fails
    for any reason is logged and skipped, so the teardown goes on to release
    the board.

    :param http: pooled HTTP client
    :type http: httpx.AsyncClient
    :param info: registry entry for the session
    :type info: AgentInfo
    :return: the run summary; None for interact sessions and when the first
        lookup fails. A run that outlasts ``BOARDFARM_AGENT_RELEASE_TIMEOUT``,
        or whose polls keep failing, comes back as the last summary read, which
        is stale: its state still says ``running``
    :rtype: dict[str, Any] | None
    """
    if info.mode == "interact":
        return None
    url = f"{info.agent_url}/run"
    headers = {SESSION_HEADER: info.session_id}
    deadline = time.monotonic() + _release_seconds()

    async def fetch() -> dict[str, Any] | None:
        response = await http.get(url, headers=headers, timeout=10.0)
        if response.status_code != HTTPStatus.OK:
            _log.info(
                "run status of %s unavailable: HTTP %s",
                info.session_id,
                response.status_code,
            )
            return None
        body = response.json()
        return body if isinstance(body, dict) else None

    async def poll() -> dict[str, Any] | None:
        try:
            return await fetch()
        except Exception as exc:  # noqa: BLE001
            _log.info("run poll of %s failed: %s", info.session_id, type(exc).__name__)
            return None

    try:
        run = await fetch()
        if run is not None and run.get("state") == "running":
            await http.post(f"{url}/cancel", headers=headers, timeout=10.0)
            run = await _wait_for_end(poll, run, deadline)
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "final run status unavailable for %s: %s",
            info.session_id,
            type(exc).__name__,
        )
        return None
    return run


async def archive_bundle(  # noqa: PLR0913
    *,
    session_id: str,
    agent_url: str,
    launcher: Launcher,
    store: DiagnosticsStore,
    http: httpx.AsyncClient,
    artifact_dir: str = _DEFAULT_ARTIFACT_ROOT,
) -> str:
    """Pull a diagnostics bundle and archive it, preferring the live agent.

    :param session_id: session to capture
    :type session_id: str
    :param agent_url: base URL of the agent; empty skips the agent tier
    :type agent_url: str
    :param launcher: launcher used for the fallback capture
    :type launcher: Launcher
    :param store: store to archive into
    :type store: DiagnosticsStore
    :param http: pooled HTTP client
    :type http: httpx.AsyncClient
    :param artifact_dir: this session's resolved artifact root (``AgentInfo
        .artifact_dir``), e.g. honouring a per-session
        ``BOARDFARM_ARTIFACT_DIR`` override in ``agent_env``
    :type artifact_dir: str
    :return: which tier produced the bundle: agent, launcher, or none
    :rtype: str
    """
    if agent_url:  # empty: the agent is known to be gone; use the launcher
        try:
            response = await http.get(
                f"{agent_url}/diagnostics/bundle",
                timeout=_BUNDLE_TIMEOUT,
                headers={SESSION_HEADER: session_id},
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            _log.info("agent bundle unavailable for %s: %s", session_id, exc)
        else:
            store.write_bundle(session_id, [response.content])
            return "agent"

    logs = await launcher.capture_logs(session_id)
    # The per-session subdirectory, not the shared root: capture_files()
    # implementations that share a filesystem across sessions (ProcessLauncher)
    # must never be handed a path that spans more than one session's files.
    session_dir = f"{artifact_dir.rstrip('/')}/{session_id}"
    files = await launcher.capture_files(session_id, session_dir)
    if not logs and not files:
        return "none"
    store.write_bundle(session_id, [_launcher_bundle(logs, files)])
    return "launcher"


def _write_meta_quietly(
    store: DiagnosticsStore, session_id: str, meta: dict[str, Any]
) -> None:
    """Write a session's metadata; log a store that cannot write it.

    A full disk must not keep the agent running or the board held: losing
    the metadata is the lesser harm.

    :param store: diagnostics store
    :type store: DiagnosticsStore
    :param session_id: session identifier
    :type session_id: str
    :param meta: the metadata to write
    :type meta: dict[str, Any]
    """
    try:
        store.write_meta(session_id, meta)
    except OSError:
        _log.exception("could not write the metadata of %s", session_id)


async def teardown_session(  # noqa: PLR0913
    *,
    session_id: str,
    info: AgentInfo,
    launcher: Launcher,
    registry: SessionRegistry,
    lease: BoardLease,
    store: DiagnosticsStore,
    http: httpx.AsyncClient,
    retain: bool,
    ended_at: float | None = None,
) -> str:
    """Cancel any run, archive, release devices, stop the container, free the board.

    Step 0 cancels a run that is still going (sessions in a non-interact mode)
    and waits for it to finish, so the bundle holds its final reports. That wait
    is bounded by ``BOARDFARM_AGENT_RELEASE_TIMEOUT``, 120 s by default, so a
    DELETE can take that long before the bundle is even pulled. The run's final
    summary goes into ``meta.json`` and onto the corpse when one is kept; a
    second pass over the same session keeps the summary already on its record.

    Steps 0, 1, 2, and 3 are best-effort: a failed run lookup, a diagnostics
    failure, a graceful-release failure, or even ``launcher.stop()`` itself
    raising (e.g. a Docker daemon ``APIError``) must never strand a board, so
    the lease is released unconditionally in a ``finally`` block. When
    ``stop()`` fails, the container's real state is unknown, so the registry
    keeps the corpse listed (``mark_dead``) instead of forgetting it, on the
    theory that a human will need to intervene on it directly.

    :param session_id: session to tear down
    :type session_id: str
    :param info: registry entry for the session
    :type info: AgentInfo
    :param launcher: launcher owning the container
    :type launcher: Launcher
    :param registry: session registry
    :type registry: SessionRegistry
    :param lease: board lease table
    :type lease: BoardLease
    :param store: diagnostics store
    :type store: DiagnosticsStore
    :param http: pooled HTTP client
    :type http: httpx.AsyncClient
    :param retain: keep the stopped container for post-mortem
    :type retain: bool
    :param ended_at: when the session ended; now when omitted (the reconciler
        passes the original time when it finishes a pending stop)
    :type ended_at: float | None
    :return: ``released``, ``retained``, or ``stop_pending`` when the host
        could not confirm the stop (the reconciler finishes it)
    :rtype: str
    """
    ended_at = time.time() if ended_at is None else ended_at

    # 0. A run still going is cancelled first, so step 1 archives its final
    # reports. For interact sessions this is a no-op.
    run = await _final_run(http, info)
    if run is None:
        # Safe to keep: info.run only ever comes from a GET /run reply (no run.env).
        run = info.run

    # 1. Capture while the agent can still answer — the only moment this works.
    source = "none"
    try:
        source = await archive_bundle(
            session_id=session_id,
            agent_url=info.agent_url,
            launcher=launcher,
            store=store,
            http=http,
            artifact_dir=info.artifact_dir,
        )
    except Exception:  # noqa: BLE001
        _log.warning("diagnostics capture failed for %s", session_id)

    _write_meta_quietly(
        store,
        session_id,
        {
            "session_id": session_id,
            "board_name": info.board_name,
            "runtime_profile": info.runtime_profile,
            "created_at": info.created_at,
            "ended_at": ended_at,
            "retained": retain,
            "bundle_source": source,
            "mode": info.mode,
            "run": run,
        },
    )

    # 2. Graceful device release, so board-side state is not left half-open.
    try:
        await http.delete(
            f"{info.agent_url}/session",
            headers={SESSION_HEADER: session_id},
            timeout=_release_timeout(),
        )
    except httpx.HTTPError as exc:
        _log.info("graceful release skipped for %s: %s", session_id, exc)

    # 3. Best-effort: a Docker daemon APIError (or any other stop() failure)
    # must not skip step 4 -- lease.release() belongs in a finally so a dead
    # agent can never strand a board, even when the container itself refuses
    # to stop.
    stop_failed = False
    pending = False
    try:
        await launcher.stop(session_id, remove=not retain)
    except StopPending:
        # The fence is at launch (host gate, pending-stop check, daemon busy
        # check), so releasing the lease below is safe.
        pending = True
        _log.warning(
            "stop of %s could not be confirmed; the reconciler will finish it",
            session_id,
        )
    except Exception:  # noqa: BLE001
        stop_failed = True
        _log.exception(
            "launcher.stop failed for %s; releasing the lease anyway",
            session_id,
        )
    finally:
        # 4. Unconditional, whatever happened above.
        await lease.release(session_id)
        # 5. A failed or pending stop means the container's real state is
        # unknown -- keep the corpse visible rather than losing it.
        if pending:
            registry.mark_dead(
                session_id, ended_at=ended_at, stop_pending=True, run=run
            )
        elif retain or stop_failed:
            registry.mark_dead(session_id, ended_at=ended_at, run=run)
        else:
            registry.remove(session_id)
    if pending:
        return "stop_pending"
    return "retained" if retain else "released"
