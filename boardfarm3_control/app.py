"""FastAPI application for the boardfarm control plane."""

from __future__ import annotations

import asyncio
import os
import secrets
import time
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import FastAPI, HTTPException, Request

from boardfarm3_control.lease import BoardLease
from boardfarm3_control.models import (
    SessionCreate,
    SessionListResponse,
    SessionResponse,
)
from boardfarm3_control.openapi import load_plugin_routers, register_plugin_routes
from boardfarm3_control.proxy import proxy_request
from boardfarm3_control.registry import SessionRegistry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import APIRouter

    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.models import AgentInfo


_HEALTH_TIMEOUT = 30.0     # seconds total for health poll — plugin-heavy agents take >5 s to start
_HEALTH_INTERVAL = 0.1     # seconds between health retries
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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await registry.rebuild(launcher)
        existing = await launcher.list_sessions()
        # Only live sessions hold a board. A retained corpse must never
        # re-acquire a lease and block its board after a restart.
        await lease.rebuild_from([s for s in existing if s.state == "live"])
        app.state.http = httpx.AsyncClient()
        yield
        # Running agents are deliberately left alone: a control plane restart
        # must not destroy live sessions or the containers being debugged.
        await app.state.http.aclose()

    app = FastAPI(title="boardfarm control plane", lifespan=lifespan)

    plugin_routers = load_plugin_routers()
    if extra_routers:
        plugin_routers.extend(extra_routers)
    register_plugin_routes(app, plugin_routers, registry)

    @app.post("/sessions", status_code=int(HTTPStatus.ACCEPTED))
    async def create_session(body: SessionCreate) -> SessionResponse:  # noqa: C901, PLR0915
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
                session_id, body.board_name, image, body.runtime_profile,
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
            await launcher.stop(session_id)
            await lease.release(session_id)
            raise HTTPException(
                status_code=int(HTTPStatus.SERVICE_UNAVAILABLE),
                detail="agent did not become healthy within 5 s",
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
            await launcher.stop(session_id)
            await lease.release(session_id)
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_REQUEST),
                detail=f"agent rejected config: {exc}",
            ) from exc
        if cfg.status_code != int(HTTPStatus.OK):
            await launcher.stop(session_id)
            await lease.release(session_id)
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_REQUEST),
                detail=f"agent rejected config: {cfg.text}",
            )

        # Boot — always called; skip_boot was already set in config options above
        boot_url = f"{agent_url}/session/boot?mode=async"
        boot_job_id: str | None = None
        try:
            async with httpx.AsyncClient() as client:
                boot = await client.post(boot_url)
        except Exception as exc:
            await launcher.stop(session_id)
            await lease.release(session_id)
            raise HTTPException(
                status_code=int(HTTPStatus.SERVICE_UNAVAILABLE),
                detail="agent boot failed",
            ) from exc
        if boot.status_code != int(HTTPStatus.ACCEPTED):
            await launcher.stop(session_id)
            await lease.release(session_id)
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_GATEWAY),
                detail=f"agent boot rejected: {boot.status_code}",
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
    async def delete_session(session_id: str) -> dict[str, str]:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )

        # Graceful teardown — ignore if agent is already dead
        agent_url = info.agent_url
        try:
            async with httpx.AsyncClient() as client:
                await client.delete(f"{agent_url}/session")
        except Exception:  # noqa: BLE001, S110
            pass

        await launcher.stop(session_id)
        registry.remove(session_id)
        await lease.release(session_id)
        return {"status": "released"}

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
