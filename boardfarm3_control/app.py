"""FastAPI application for the boardfarm control plane."""

from __future__ import annotations

import asyncio
import os
import secrets
import time
from contextlib import asynccontextmanager, suppress
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from boardfarm3_control.lease import BoardLease
from boardfarm3_control.models import (
    SessionCreate,
    SessionListResponse,
    SessionResponse,
)
from boardfarm3_control.openapi import load_plugin_routers, register_plugin_routes
from boardfarm3_control.proxy import proxy_request
from boardfarm3_control.reaper import run_reaper
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore
from boardfarm3_control.teardown import archive_bundle, teardown_session

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import APIRouter

    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.models import AgentInfo


_HEALTH_TIMEOUT = (
    30.0  # seconds total for health poll — plugin-heavy agents take >5 s to start
)
_HEALTH_INTERVAL = 0.1  # seconds between health retries
# seconds per-agent for GET /sessions fan-out
_STATE_TIMEOUT = float(os.environ.get("BOARDFARM_STATE_TIMEOUT", "2.0"))
_MAX_LIMIT = 100


def _new_session_id() -> str:
    return f"s-{secrets.token_hex(4)}"


def create_app(  # noqa: C901, PLR0915
    launcher: Launcher,
    profiles: dict[str, str],
    extra_routers: list[APIRouter] | None = None,
) -> FastAPI:
    """Build the control plane application.

    :param launcher: container lifecycle manager
    :type launcher: Launcher
    :param profiles: mapping of profile name to Docker image
    :type profiles: dict[str, str]
    :param extra_routers: additional plugin routers to include (used in tests)
    :type extra_routers: list[APIRouter] | None
    :return: FastAPI application
    :rtype: FastAPI
    """
    lease = BoardLease()
    registry = SessionRegistry()
    store = DiagnosticsStore()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await registry.rebuild(launcher)
        existing = await launcher.list_sessions()
        # Only live sessions hold a board. A retained corpse must never
        # re-acquire a lease and block its board after a restart.
        await lease.rebuild_from([s for s in existing if s.state == "live"])
        app.state.http = httpx.AsyncClient()
        app.state.reaper = asyncio.create_task(
            run_reaper(launcher=launcher, registry=registry, store=store),
        )
        yield
        # Running agents are deliberately left alone: a control plane restart
        # must not destroy live sessions or the containers being debugged.
        app.state.reaper.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.reaper
        await app.state.http.aclose()

    app = FastAPI(title="boardfarm control plane", lifespan=lifespan)
    # Exposed for tests that need to drive the reaper or inspect store/registry
    # state directly against the exact instances this app is wired to.
    app.state.registry = registry
    app.state.store = store
    app.state.launcher = launcher

    plugin_routers = load_plugin_routers()
    if extra_routers:
        plugin_routers.extend(extra_routers)
    register_plugin_routes(app, plugin_routers, registry)

    async def _unwind(  # noqa: PLR0913
        session_id: str,
        info: AgentInfo,
        http: httpx.AsyncClient,
        status: HTTPStatus,
        error: str,
        message: str,
    ) -> HTTPException:
        """Retain the failed container and build the error to raise.

        :param session_id: failed session
        :type session_id: str
        :param info: registry entry for the failed session
        :type info: AgentInfo
        :param http: pooled HTTP client
        :type http: httpx.AsyncClient
        :param status: HTTP status to return
        :type status: HTTPStatus
        :param error: machine-readable error name
        :type error: str
        :param message: human-readable detail
        :type message: str
        :return: the exception the caller should raise
        :rtype: HTTPException
        """
        registry.add(info)
        await teardown_session(
            session_id=session_id,
            info=info,
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=store,
            http=http,
            retain=True,
        )
        return HTTPException(
            status_code=int(status),
            detail={
                "error": error,
                "message": message,
                "session_id": session_id,
                "diagnostics": f"/sessions/{session_id}/diagnostics",
            },
        )

    @app.post("/sessions", status_code=int(HTTPStatus.ACCEPTED))
    async def create_session(  # noqa: C901, PLR0915
        body: SessionCreate,
        request: Request,
    ) -> SessionResponse:
        if body.runtime_profile not in profiles:
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_REQUEST),
                detail=f"unknown runtime_profile {body.runtime_profile!r}",
            )

        session_id = _new_session_id()
        acquired = await lease.acquire(body.board_name, session_id)
        if not acquired:
            held = lease.held_by(body.board_name)
            raise HTTPException(
                status_code=int(HTTPStatus.CONFLICT),
                detail=f"board {body.board_name} is held by session {held}",
            )

        image = profiles[body.runtime_profile]
        try:
            info = await launcher.start(
                session_id,
                body.board_name,
                image,
                body.runtime_profile,
                agent_env=body.agent_env or None,
            )
        except Exception as exc:
            await lease.release(session_id)
            raise HTTPException(
                status_code=int(HTTPStatus.SERVICE_UNAVAILABLE),
                detail=f"failed to start container: {exc}",
            ) from exc

        agent_url = info.agent_url

        # Health poll: 5 s total, 100 ms interval
        healthy = False
        deadline = time.monotonic() + _HEALTH_TIMEOUT
        async with httpx.AsyncClient() as client:
            while time.monotonic() < deadline:
                try:
                    resp = await client.get(f"{agent_url}/health")
                    if resp.status_code == int(HTTPStatus.OK):
                        healthy = True
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(_HEALTH_INTERVAL)

        if not healthy:
            raise await _unwind(
                session_id,
                info,
                request.app.state.http,
                HTTPStatus.SERVICE_UNAVAILABLE,
                "AgentUnhealthy",
                f"agent did not become healthy within {_HEALTH_TIMEOUT} s",
            )

        # Configure agent — inject skip_boot when caller did not request a full boot
        # (skip_boot is a config-time option, not a boot-URL parameter)
        config_options: dict[str, Any] = dict(body.options)
        if not body.boot:
            config_options.setdefault("skip_boot", True)
        try:
            async with httpx.AsyncClient() as client:
                cfg = await client.post(
                    f"{agent_url}/session/config",
                    json={"payload": body.payload, "options": config_options},
                )
        except Exception as exc:
            raise await _unwind(
                session_id,
                info,
                request.app.state.http,
                HTTPStatus.BAD_REQUEST,
                "AgentConfigRejected",
                f"agent rejected config: {exc}",
            ) from exc
        if cfg.status_code != int(HTTPStatus.OK):
            raise await _unwind(
                session_id,
                info,
                request.app.state.http,
                HTTPStatus.BAD_REQUEST,
                "AgentConfigRejected",
                f"agent rejected config: {cfg.text}",
            )

        # Boot — always called; skip_boot was already set in config options above
        boot_url = f"{agent_url}/session/boot?mode=async"
        boot_job_id: str | None = None
        try:
            async with httpx.AsyncClient() as client:
                boot = await client.post(boot_url)
        except Exception as exc:
            raise await _unwind(
                session_id,
                info,
                request.app.state.http,
                HTTPStatus.SERVICE_UNAVAILABLE,
                "AgentBootUnreachable",
                f"agent boot failed: {exc}",
            ) from exc
        if boot.status_code != int(HTTPStatus.ACCEPTED):
            raise await _unwind(
                session_id,
                info,
                request.app.state.http,
                HTTPStatus.BAD_GATEWAY,
                "AgentBootRejected",
                f"agent boot rejected: {boot.status_code}",
            )
        boot_job_id = boot.json().get("boot_job_id")
        session_state = "booting" if body.boot else "ready"

        registry.add(info)
        registry.touch(session_id)

        return SessionResponse(
            session_id=session_id,
            board_name=info.board_name,
            runtime_profile=info.runtime_profile,
            state=session_state,
            boot_job_id=boot_job_id,
            booted=False,
            agent_url=info.agent_url,
            pid=info.pid,
            created_at=info.created_at,
            last_activity=registry.last_activity(session_id),
        )

    @app.get("/sessions")
    async def list_sessions(offset: int = 0, limit: int = 20) -> SessionListResponse:
        limit = min(limit, _MAX_LIMIT)
        page, total = registry.list_page(offset, limit)

        async def fetch_state(info: AgentInfo) -> SessionResponse:
            if info.state == "dead":
                return SessionResponse(
                    session_id=info.session_id,
                    board_name=info.board_name,
                    runtime_profile=info.runtime_profile,
                    state="dead",
                    booted=False,
                    agent_url=info.agent_url,
                    pid=info.pid,
                    created_at=info.created_at,
                    ended_at=info.ended_at,
                    last_activity=registry.last_activity(info.session_id),
                    liveness=None,
                )
            last_act: float | None
            liveness: dict[str, Any] | None
            try:
                async with httpx.AsyncClient() as client:
                    resp = await asyncio.wait_for(
                        client.get(f"{info.agent_url}/session"),
                        timeout=_STATE_TIMEOUT,
                    )
                data: dict[str, Any] = resp.json()
                state: str = data.get("state", "unknown")
                booted: bool = bool(data.get("booted", False))
                last_act = data.get("last_activity")
                liveness = data.get("liveness")
                if last_act is not None:
                    registry.touch(info.session_id)
            except (asyncio.TimeoutError, httpx.TransportError):
                state = "unreachable"
                booted = False
                last_act = registry.last_activity(info.session_id)
                liveness = None
            return SessionResponse(
                session_id=info.session_id,
                board_name=info.board_name,
                runtime_profile=info.runtime_profile,
                state=state,
                booted=booted,
                agent_url=info.agent_url,
                pid=info.pid,
                created_at=info.created_at,
                ended_at=info.ended_at,
                last_activity=last_act,
                liveness=liveness,
            )

        sessions = await asyncio.gather(*[fetch_state(info) for info in page])
        return SessionListResponse(
            sessions=list(sessions),
            total=total,
            offset=offset,
            limit=limit,
        )

    @app.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        request: Request,
        retain: bool = False,
        purge: bool = False,
    ) -> dict[str, str]:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        if retain and purge:
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_REQUEST),
                detail="retain and purge are mutually exclusive",
            )
        if info.state == "dead":
            if retain:
                # Explicit request to keep the corpse: it is already
                # retained, so this is a no-op rather than a silent purge.
                return {"status": "retained"}
            # Bare DELETE or ?purge=true: purge the corpse and its bundle.
            await launcher.purge(session_id)
            store.delete(session_id)
            registry.remove(session_id)
            return {"status": "purged"}
        await teardown_session(
            session_id=session_id,
            info=info,
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=store,
            http=request.app.state.http,
            retain=retain,
        )
        return {"status": "retained" if retain else "released"}

    @app.post("/sessions/{session_id}/diagnostics/snapshot")
    async def diagnostics_snapshot(
        session_id: str,
        request: Request,
    ) -> dict[str, Any]:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        source = await archive_bundle(
            session_id=session_id,
            agent_url=info.agent_url,
            launcher=launcher,
            store=store,
            http=request.app.state.http,
            artifact_dir=info.artifact_dir,
        )
        if source == "none":
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_GATEWAY),
                detail="agent unreachable and launcher capture produced nothing",
            )
        captured_at = time.time()
        # A snapshot is a "last touched" evidence capture, not a death record:
        # this is on a session that may still be perfectly healthy. Writing
        # meta.json here (which archive_bundle()/write_bundle() never does on
        # its own) is what keeps the reaper's aged-bundle sweep from treating
        # a missing ended_at as "infinitely old" and deleting it on the very
        # next pass.
        store.write_meta(
            session_id,
            {
                "session_id": session_id,
                "board_name": info.board_name,
                "runtime_profile": info.runtime_profile,
                "created_at": info.created_at,
                "ended_at": captured_at,
                "retained": False,
                "bundle_source": source,
            },
        )
        path = store.bundle_path(session_id)
        return {
            "path": str(path),
            "size": path.stat().st_size,
            "source": source,
            "captured_at": captured_at,
        }

    @app.get("/sessions/{session_id}/diagnostics")
    async def diagnostics(session_id: str, request: Request) -> object:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        attempted: list[str] = []
        # Tier 1 — live agent: stream straight through, nothing buffered.
        if info.state == "live":
            try:
                return await proxy_request(
                    request,
                    info.agent_url,
                    "diagnostics/bundle",
                    client=request.app.state.http,
                    session_id=session_id,
                )
            except HTTPException:
                attempted.append("agent: unreachable")
        else:
            attempted.append("agent: session is dead")
        # Tier 2 — archived bundle.
        if store.has_bundle(session_id):
            return FileResponse(
                store.bundle_path(session_id),
                media_type="application/gzip",
                filename=f"{session_id}-diagnostics.tar.gz",
            )
        attempted.append("archive: no bundle stored")
        # Tier 3 — build one now from the launcher.
        source = await archive_bundle(
            session_id=session_id,
            agent_url=info.agent_url,
            launcher=launcher,
            store=store,
            http=request.app.state.http,
            artifact_dir=info.artifact_dir,
        )
        if source != "none":
            return FileResponse(
                store.bundle_path(session_id),
                media_type="application/gzip",
                filename=f"{session_id}-diagnostics.tar.gz",
            )
        attempted.append("launcher: capture produced nothing")
        raise HTTPException(
            status_code=int(HTTPStatus.NOT_FOUND),
            detail={"error": "NoDiagnostics", "attempted": attempted},
        )

    # Catch-all proxy for everything else under /sessions/{session_id}/
    @app.api_route(
        "/sessions/{session_id}/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def proxy(session_id: str, path: str, request: Request) -> object:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        registry.touch(session_id)
        return await proxy_request(
            request,
            info.agent_url,
            path,
            client=request.app.state.http,
            session_id=session_id,
        )

    return app
