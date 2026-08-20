"""The single teardown sequence used by DELETE and by every failure unwind."""

from __future__ import annotations

import io
import logging
import tarfile
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.lease import BoardLease
    from boardfarm3_control.models import AgentInfo
    from boardfarm3_control.registry import SessionRegistry
    from boardfarm3_control.store import DiagnosticsStore

_log = logging.getLogger(__name__)
_BUNDLE_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
# Matches boardfarm3_control.launcher._DEFAULT_ARTIFACT_ROOT and
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
    :param agent_url: base URL of the agent
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
    try:
        response = await http.get(
            f"{agent_url}/diagnostics/bundle",
            timeout=_BUNDLE_TIMEOUT,
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
) -> None:
    """Archive, release devices, stop the container, and free the board.

    Steps 1, 2, and 3 are best-effort: a diagnostics failure, a graceful-
    release failure, or even ``launcher.stop()`` itself raising (e.g. a
    Docker daemon ``APIError``) must never strand a board, so the lease is
    released unconditionally in a ``finally`` block. When ``stop()`` fails,
    the container's real state is unknown, so the registry keeps the corpse
    listed (``mark_dead``) instead of forgetting it, on the theory that a
    human will need to intervene on it directly.

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
    """
    ended_at = time.time()

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

    store.write_meta(
        session_id,
        {
            "session_id": session_id,
            "board_name": info.board_name,
            "runtime_profile": info.runtime_profile,
            "created_at": info.created_at,
            "ended_at": ended_at,
            "retained": retain,
            "bundle_source": source,
        },
    )

    # 2. Graceful device release, so board-side state is not left half-open.
    try:
        await http.delete(f"{info.agent_url}/session")
    except httpx.HTTPError as exc:
        _log.info("graceful release skipped for %s: %s", session_id, exc)

    # 3. Best-effort: a Docker daemon APIError (or any other stop() failure)
    # must not skip step 4 -- lease.release() belongs in a finally so a dead
    # agent can never strand a board, even when the container itself refuses
    # to stop.
    stop_failed = False
    try:
        await launcher.stop(session_id, remove=not retain)
    except Exception:  # noqa: BLE001
        stop_failed = True
        _log.exception(
            "launcher.stop failed for %s; releasing the lease anyway",
            session_id,
        )
    finally:
        # 4. Unconditional, whatever happened above.
        await lease.release(session_id)
        # 5. A failed stop() means the container's real state is unknown --
        # keep the corpse visible in the registry rather than losing it, so a
        # human can still find and intervene on it directly.
        if retain or stop_failed:
            registry.mark_dead(session_id, ended_at=ended_at)
        else:
            registry.remove(session_id)
