"""FastAPI application for the boardfarm control plane."""

from __future__ import annotations

import asyncio
import logging
import os
import posixpath
import secrets
import time
from collections import Counter
from contextlib import asynccontextmanager, suppress
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from boardfarm3.api import SESSION_HEADER
from boardfarm3.api.entrypoints import plugin_versions
from boardfarm3.api.modes import INTERACT, load_plugin_modes
from boardfarm3.api.routers import DISABLED_PLUGINS_ENV
from boardfarm3_control import __version__
from boardfarm3_control.admin import build_admin_router
from boardfarm3_control.errors import (
    BoardNotInInventory,
    BoardPendingStop,
    ControlError,
    HostDraining,
    HostUnreachable,
    ManagedByControl,
    SessionNotLive,
    UnknownMode,
)
from boardfarm3_control.expiry import run_expiry
from boardfarm3_control.launcher import MultiHostLauncher
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.models import (
    SessionCreate,
    SessionListResponse,
    SessionResponse,
)
from boardfarm3_control.openapi import load_plugin_routers, register_plugin_routes
from boardfarm3_control.placement import resolve_host
from boardfarm3_control.proxy import _client_or_default, proxy_request
from boardfarm3_control.reaper import run_reaper
from boardfarm3_control.reconcile import (
    DEFAULT_RECONCILE_INTERVAL,
    RECONCILE_INTERVAL_ENV,
    Reconciler,
)
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore
from boardfarm3_control.teardown import archive_bundle, teardown_session

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from fastapi import APIRouter

    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.models import AgentInfo


_log = logging.getLogger(__name__)

_HEALTH_TIMEOUT = (
    30.0  # seconds total for health poll — plugin-heavy agents take >5 s to start
)
_HEALTH_INTERVAL = 0.1  # seconds between health retries
# seconds per-agent for GET /sessions fan-out
_STATE_TIMEOUT = float(os.environ.get("BOARDFARM_STATE_TIMEOUT", "2.0"))
_MAX_LIMIT = 100
# Agent paths whose non-GET calls change its lifecycle; only control may make them.
_LIFECYCLE_PATHS = frozenset({"session", "session/config", "session/boot"})
_PROXY_MAX_CONNECTIONS_ENV = "BOARDFARM_PROXY_MAX_CONNECTIONS"
_PROXY_KEEPALIVE_CAP = 100
# Configuring parses the inventory and constructs every device in the agent.
_CONFIG_TIMEOUT_ENV = "BOARDFARM_AGENT_CONFIG_TIMEOUT"
_DEFAULT_CONFIG_TIMEOUT = 120.0


def _config_timeout() -> float:
    """Return the seconds an agent may take to configure a session.

    :return: ``BOARDFARM_AGENT_CONFIG_TIMEOUT``, default 120
    :rtype: float
    """
    return float(os.environ.get(_CONFIG_TIMEOUT_ENV, str(_DEFAULT_CONFIG_TIMEOUT)))


def _proxy_limits() -> httpx.Limits:
    """Return connection limits for the shared agent client.

    Every open console stream holds a connection for as long as it runs, so
    httpx's default of 100 would starve other proxied calls at ~100 users.

    :return: limits from ``BOARDFARM_PROXY_MAX_CONNECTIONS`` (default 500)
    :rtype: httpx.Limits
    """
    max_connections = int(os.environ.get(_PROXY_MAX_CONNECTIONS_ENV, "500"))
    return httpx.Limits(
        max_connections=max_connections,
        max_keepalive_connections=min(max_connections, _PROXY_KEEPALIVE_CAP),
    )


_STRICT_VERSIONS_ENV = "BOARDFARM_REQUIRE_MATCHING_VERSIONS"


def _version_mismatch(ours: dict[str, str], theirs: object) -> list[str]:
    """Describe how the agent's code differs from control's.

    :param ours: control's ``plugin_versions()``
    :type ours: dict[str, str]
    :param theirs: the ``versions`` the agent reported, if any
    :type theirs: object
    :return: one line per difference; empty when they match
    :rtype: list[str]
    """
    if not isinstance(theirs, dict):
        return ["the agent does not report its versions: its image predates this check"]
    differences: list[str] = []
    for name in sorted(ours.keys() | theirs.keys()):
        agent, control = theirs.get(name), ours.get(name)
        if agent == control:
            continue
        if agent is None:
            differences.append(f"agent lacks {name} {control}")
        elif control is None:
            differences.append(f"agent has {name} {agent}; control does not")
        else:
            differences.append(f"agent has {name} {agent}; control has {control}")
    return differences


def _json_object(response: httpx.Response) -> dict[str, Any] | None:
    """Return a 2xx response's JSON object body, or None.

    :param response: an agent response
    :type response: httpx.Response
    :return: the decoded object, or None when absent or malformed
    :rtype: dict[str, Any] | None
    """
    if not response.is_success:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _reconcile_interval() -> float:
    """Return seconds between reconcile passes.

    :return: ``BOARDFARM_RECONCILE_INTERVAL``, default 30
    :rtype: float
    """
    return float(
        os.environ.get(RECONCILE_INTERVAL_ENV, str(DEFAULT_RECONCILE_INTERVAL))
    )


def _sid(session_id: str) -> dict[str, str]:
    """Return the header that addresses an agent call to *session_id*.

    :param session_id: session the call is for
    :type session_id: str
    :return: headers to send
    :rtype: dict[str, str]
    """
    return {SESSION_HEADER: session_id}


async def _wait_healthy(
    client: httpx.AsyncClient,
    agent_url: str,
    session_id: str,
) -> dict[str, Any] | None:
    """Poll the agent's /health until it answers 200 or the deadline passes.

    :param client: client to poll with
    :type client: httpx.AsyncClient
    :param agent_url: the agent's base URL
    :type agent_url: str
    :param session_id: session the agent must be serving
    :type session_id: str
    :return: the health body once healthy, or None when the deadline passed
    :rtype: dict[str, Any] | None
    """
    deadline = time.monotonic() + _HEALTH_TIMEOUT
    while time.monotonic() < deadline:
        try:
            resp = await client.get(f"{agent_url}/health", headers=_sid(session_id))
            if resp.status_code == int(HTTPStatus.OK):
                return _json_object(resp) or {}
        except httpx.TransportError:
            pass
        await asyncio.sleep(_HEALTH_INTERVAL)
    return None


def _new_session_id() -> str:
    return f"s-{secrets.token_hex(4)}"


def _agent_env(requested: dict[str, str] | None) -> dict[str, str] | None:
    """Merge the control plane's plugin deny-list into an agent environment.

    An explicit value in the session-create body wins, so a caller can opt a
    single session out. ``DockerLauncher`` already spreads this mapping into the
    container environment and ``ProcessLauncher`` inherits ``os.environ``, so
    seeding here covers both launchers.

    :param requested: agent_env from the session-create body, if any
    :type requested: dict[str, str] | None
    :return: the environment to pass to the launcher, or None when empty
    :rtype: dict[str, str] | None
    """
    env = dict(requested or {})
    disabled = os.environ.get(DISABLED_PLUGINS_ENV)
    if disabled and DISABLED_PLUGINS_ENV not in env:
        env[DISABLED_PLUGINS_ENV] = disabled
    return env or None


def create_app(  # noqa: C901, PLR0915
    launcher: Launcher,
    profiles: dict[str, str],
    extra_routers: list[APIRouter] | None = None,
    cors_origins: list[str] | None = None,
    modes: Iterable[str] | None = None,
) -> FastAPI:
    """Build the control plane application.

    :param launcher: container lifecycle manager
    :type launcher: Launcher
    :param profiles: mapping of profile name to Docker image
    :type profiles: dict[str, str]
    :param extra_routers: additional plugin routers to include (used in tests)
    :type extra_routers: list[APIRouter] | None
    :param cors_origins: browser origins allowed to call the API cross-origin;
        None or empty keeps the control plane same-origin only
    :type cors_origins: list[str] | None
    :param modes: session modes on offer besides ``interact``; None discovers
        them from the installed ``boardfarm_api`` plugins
    :type modes: Iterable[str] | None
    :return: FastAPI application
    :rtype: FastAPI
    """
    lease = BoardLease()
    registry = SessionRegistry()
    store = DiagnosticsStore()
    inflight: set[str] = set()
    local_versions = plugin_versions()
    available_modes = frozenset(
        {INTERACT, *(modes if modes is not None else load_plugin_modes())}
    )
    hosts = launcher.hosts if isinstance(launcher, MultiHostLauncher) else None
    reconciler: Reconciler | None = None
    if isinstance(launcher, MultiHostLauncher):
        reconciler = Reconciler(
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=store,
            inflight=inflight,
            http_for=lambda info: launcher.agent_client(info) or app.state.http,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.http = httpx.AsyncClient(limits=_proxy_limits())
        background: list[asyncio.Task[None]] = []
        if reconciler is not None:
            # Replaces the label rebuild: restore sessions.json, then ask every
            # reachable host (bounded per host, so a dead host cannot hang startup).
            await reconciler.startup()
            app.state.reconcile = asyncio.create_task(
                reconciler.run(_reconcile_interval())
            )
            background.append(app.state.reconcile)
        else:
            await registry.rebuild(launcher)
            existing = await launcher.list_sessions()
            # Only live sessions hold a board. A retained corpse must never
            # re-acquire a lease and block its board after a restart.
            await lease.rebuild_from([s for s in existing if s.state == "live"])
        app.state.reaper = asyncio.create_task(
            run_reaper(launcher=launcher, registry=registry, store=store),
        )
        background.append(app.state.reaper)
        app.state.expiry = asyncio.create_task(
            run_expiry(
                registry=registry,
                launcher=launcher,
                lease=lease,
                store=store,
                inflight=inflight,
                http_for=lambda info: launcher.agent_client(info) or app.state.http,
            ),
        )
        background.append(app.state.expiry)
        yield
        # Running agents are deliberately left alone: a control plane restart
        # must not destroy live sessions or the containers being debugged.
        for task in background:
            task.cancel()
        for task in background:
            with suppress(asyncio.CancelledError):
                await task
        await app.state.http.aclose()

    app = FastAPI(title="boardfarm control plane", lifespan=lifespan)
    if cors_origins:
        # Browser GUIs on another origin (e.g. a scheduler page) need the
        # preflight answered and the response headers set, or the browser
        # discards a response the control plane has already acted on.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    # Exposed for tests that need to drive the reaper or inspect store/registry
    # state directly against the exact instances this app is wired to.
    app.state.registry = registry
    app.state.store = store
    app.state.launcher = launcher
    app.state.inflight = inflight
    app.state.lease = lease
    app.state.reconciler = reconciler
    if isinstance(launcher, MultiHostLauncher):
        app.include_router(
            build_admin_router(launcher=launcher, registry=registry, lease=lease)
        )

    @app.exception_handler(ControlError)
    async def control_error(_request: Request, exc: ControlError) -> JSONResponse:
        return JSONResponse(
            status_code=int(exc.status), content={"detail": exc.detail()}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # The default 422 echoes each failing input, so run.env and credentials leak.
        errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
        return JSONResponse(
            status_code=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            content={"detail": jsonable_encoder(errors)},
        )

    def _agent_http(info: AgentInfo) -> httpx.AsyncClient | None:
        # The launcher's per-host client when it has one, else the shared
        # pool; None before the lifespan has created the pool.
        return launcher.agent_client(info) or getattr(app.state, "http", None)

    def _agent_http_or_pool(info: AgentInfo, request: Request) -> httpx.AsyncClient:
        return launcher.agent_client(info) or request.app.state.http

    plugin_routers = load_plugin_routers()
    if extra_routers:
        plugin_routers.extend(extra_routers)
    register_plugin_routes(app, plugin_routers, registry, client_for=_agent_http)

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
                "host": info.host,
                "diagnostics": f"/sessions/{session_id}/diagnostics",
            },
        )

    unwinding: set[asyncio.Task[None]] = set()

    def _unwind_in_background(session_id: str, info: AgentInfo) -> None:
        # The create was cancelled (client gone) after the container started.
        # Without this the reconciler adopts it: a session nobody asked for,
        # holding the board until someone deletes it.
        async def _teardown() -> None:
            inflight.add(session_id)
            try:
                registry.add(info)
                await teardown_session(
                    session_id=session_id,
                    info=info,
                    launcher=launcher,
                    registry=registry,
                    lease=lease,
                    store=store,
                    http=launcher.agent_client(info) or app.state.http,
                    retain=False,
                )
            finally:
                inflight.discard(session_id)

        task = asyncio.get_running_loop().create_task(_teardown())
        unwinding.add(task)
        task.add_done_callback(unwinding.discard)

    async def _check_agent_versions(
        session_id: str,
        info: AgentInfo,
        health: dict[str, Any],
        request: Request,
    ) -> list[str]:
        # Control builds the unified OpenAPI from its own plugins; an agent
        # image with different ones 404s some of those routes.
        mismatch = _version_mismatch(local_versions, health.get("versions"))
        if mismatch and os.environ.get(_STRICT_VERSIONS_ENV, "") not in ("", "0"):
            raise await _unwind(
                session_id,
                info,
                _agent_http_or_pool(info, request),
                HTTPStatus.CONFLICT,
                "AgentVersionMismatch",
                "; ".join(mismatch),
            )
        if mismatch:
            _log.warning(
                "agent for %s runs different code: %s", session_id, "; ".join(mismatch)
            )
        return mismatch

    def _placement_gate(body: SessionCreate) -> str | None:
        if hosts is None:
            return None
        host_name = resolve_host(body.payload, body.board_name, hosts)
        docker_host = hosts.docker_host(host_name)
        if docker_host.spec.drain:
            msg = f"host {host_name} is draining"
            raise HostDraining(msg, host=host_name)
        if docker_host.is_down:
            msg = f"host {host_name} is unreachable"
            raise HostUnreachable(
                msg, host=host_name, last_error=docker_host.last_error
            )
        return host_name

    async def _launch(  # noqa: C901, PLR0912, PLR0915
        session_id: str,
        body: SessionCreate,
        image: str,
        host_name: str | None,
        request: Request,
    ) -> SessionResponse:
        # host= is passed only when placement chose one, so Launcher
        # subclasses whose start() predates the parameter keep working.
        placement = {"host": host_name} if host_name is not None else {}
        try:
            info = await launcher.start(
                session_id,
                body.board_name,
                image,
                body.runtime_profile,
                agent_env=_agent_env(body.agent_env),
                **placement,
            )
        except ControlError:
            await lease.release(session_id)
            raise
        except Exception as exc:
            await lease.release(session_id)
            where = f" on host {host_name}" if host_name else ""
            raise HTTPException(
                status_code=int(HTTPStatus.SERVICE_UNAVAILABLE),
                detail=f"failed to start container{where}: {exc}",
            ) from exc
        except BaseException:
            # A cancelled create (client gone, pool shut down) must not strand
            # the board's lease until the next restart.
            await lease.release(session_id)
            raise

        agent_url = info.agent_url
        client, owns_client = _client_or_default(_agent_http(info))
        warnings: list[str] = []
        try:
            health = await _wait_healthy(client, agent_url, session_id)
            if health is None:
                raise await _unwind(
                    session_id,
                    info,
                    _agent_http_or_pool(info, request),
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "AgentUnhealthy",
                    f"agent did not become healthy within {_HEALTH_TIMEOUT} s",
                )
            warnings.extend(
                await _check_agent_versions(session_id, info, health, request)
            )
            config_options: dict[str, Any] = dict(body.options)
            if not body.boot:
                config_options.setdefault("skip_boot", True)
            config_timeout = _config_timeout()
            try:
                cfg = await client.post(
                    f"{agent_url}/session/config",
                    json={"payload": body.payload, "options": config_options},
                    headers=_sid(session_id),
                    timeout=httpx.Timeout(
                        connect=10.0, read=config_timeout, write=30.0, pool=10.0
                    ),
                )
            except httpx.TimeoutException as exc:
                raise await _unwind(
                    session_id,
                    info,
                    _agent_http_or_pool(info, request),
                    HTTPStatus.GATEWAY_TIMEOUT,
                    "AgentConfigTimeout",
                    f"agent did not finish configuring within {config_timeout:.0f} s",
                ) from exc
            except Exception as exc:
                raise await _unwind(
                    session_id,
                    info,
                    _agent_http_or_pool(info, request),
                    HTTPStatus.BAD_REQUEST,
                    "AgentConfigRejected",
                    f"agent rejected config: {exc}",
                ) from exc
            if cfg.status_code != int(HTTPStatus.OK):
                raise await _unwind(
                    session_id,
                    info,
                    _agent_http_or_pool(info, request),
                    HTTPStatus.BAD_REQUEST,
                    "AgentConfigRejected",
                    f"agent rejected config: {cfg.text}",
                )
            try:
                boot = await client.post(
                    f"{agent_url}/session/boot?mode=async",
                    headers=_sid(session_id),
                )
            except Exception as exc:
                raise await _unwind(
                    session_id,
                    info,
                    _agent_http_or_pool(info, request),
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "AgentBootUnreachable",
                    f"agent boot failed: {exc}",
                ) from exc
            if boot.status_code != int(HTTPStatus.ACCEPTED):
                raise await _unwind(
                    session_id,
                    info,
                    _agent_http_or_pool(info, request),
                    HTTPStatus.BAD_GATEWAY,
                    "AgentBootRejected",
                    f"agent boot rejected: {boot.status_code}",
                )
        except asyncio.CancelledError:
            _unwind_in_background(session_id, info)
            raise
        finally:
            if owns_client:
                await client.aclose()

        registry.add(info)
        registry.touch(session_id)
        booting = _json_object(boot) or {}
        return SessionResponse(
            session_id=session_id,
            board_name=info.board_name,
            runtime_profile=info.runtime_profile,
            # Even with boot=false the agent runs a connect job first: report
            # what the agent says, never a "ready" it has not reached.
            state=booting.get("state") or "booting",
            boot_job_id=booting.get("boot_job_id"),
            booted=False,
            agent_url=info.agent_url,
            pid=info.pid,
            created_at=info.created_at,
            last_activity=registry.last_activity(session_id),
            host=info.host,
            image_id=info.image_id,
            warnings=warnings,
        )

    @app.post("/sessions", status_code=int(HTTPStatus.ACCEPTED))
    async def create_session(body: SessionCreate, request: Request) -> SessionResponse:
        if body.runtime_profile not in profiles:
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_REQUEST),
                detail=f"unknown runtime_profile {body.runtime_profile!r}",
            )
        if body.mode not in available_modes:
            msg = f"mode {body.mode!r} is not offered by this control plane"
            raise UnknownMode(msg, modes=sorted(available_modes))
        inventory = body.payload.get("inventory")
        if isinstance(inventory, dict) and body.board_name not in inventory:
            # Found out now, not after an image pull and a container start.
            msg = f"payload.inventory has no entry for board {body.board_name}"
            raise BoardNotInInventory(msg, board_name=body.board_name)
        host_name = _placement_gate(body)
        pending = registry.pending_stop_for(body.board_name)
        if pending is not None:
            msg = f"board {body.board_name} has a stop pending on host {pending.host}"
            raise BoardPendingStop(
                msg, session_id=pending.session_id, host=pending.host
            )

        session_id = _new_session_id()
        acquired = await lease.acquire(body.board_name, session_id)
        if not acquired:
            held = lease.held_by(body.board_name)
            where = f" on host {host_name}" if host_name else ""
            raise HTTPException(
                status_code=int(HTTPStatus.CONFLICT),
                detail=f"board {body.board_name} is held by session {held}{where}",
            )
        inflight.add(session_id)
        try:
            return await _launch(
                session_id,
                body,
                profiles[body.runtime_profile],
                host_name,
                request,
            )
        finally:
            inflight.discard(session_id)

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
                host=info.host,
                image_id=info.image_id,
                stop_pending=info.stop_pending,
            )
        last_act: float | None
        liveness: dict[str, Any] | None
        client, owns_client = _client_or_default(_agent_http(info))
        try:
            resp = await asyncio.wait_for(
                client.get(f"{info.agent_url}/session", headers=_sid(info.session_id)),
                timeout=_STATE_TIMEOUT,
            )
            # A 500 or a non-JSON reply from one agent must not fail the
            # whole listing.
            data = _json_object(resp) or {}
            state: str = data.get("state", "unknown")
            booted: bool = bool(data.get("booted", False))
            last_act = data.get("last_activity")
            liveness = data.get("liveness")
        except (asyncio.TimeoutError, httpx.TransportError):
            state = "unreachable"
            booted = False
            last_act = registry.last_activity(info.session_id)
            liveness = None
        finally:
            if owns_client:
                await client.aclose()
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
            host=info.host,
            image_id=info.image_id,
            stop_pending=info.stop_pending,
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        counts = Counter(info.state for info in registry.sessions())
        return {
            "status": "ok",
            "version": __version__,
            "control_id": getattr(launcher, "control_id", None),
            "versions": local_versions,
            "modes": sorted(available_modes),
            "sessions": {"live": counts["live"], "dead": counts["dead"]},
        }

    @app.get("/sessions")
    async def list_sessions(offset: int = 0, limit: int = 20) -> SessionListResponse:
        limit = min(limit, _MAX_LIMIT)
        page, total = registry.list_page(offset, limit)
        sessions = await asyncio.gather(*[fetch_state(info) for info in page])
        return SessionListResponse(
            sessions=list(sessions),
            total=total,
            offset=offset,
            limit=limit,
        )

    @app.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> SessionResponse:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        return await fetch_state(info)

    @app.delete("/sessions/{session_id}", response_model=None)
    async def delete_session(
        session_id: str,
        request: Request,
        retain: bool = False,
        purge: bool = False,
    ) -> dict[str, str] | JSONResponse:
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
        if session_id in inflight:
            raise HTTPException(
                status_code=int(HTTPStatus.CONFLICT),
                detail=f"session {session_id} is already being created or torn down",
            )
        if info.state == "dead":
            if retain:
                # Explicit request to keep the corpse: it is already
                # retained, so this is a no-op rather than a silent purge.
                return {"status": "retained"}
            # Bare DELETE or ?purge=true. On a pending stop whose host is still
            # unreachable, purge raises HostUnreachable (503) and nothing changes.
            await launcher.purge(session_id)
            store.delete(session_id)
            registry.remove(session_id)
            # A dead session should hold no lease; release anyway so a corpse
            # can never strand its board.
            await lease.release(session_id)
            return {"status": "purged"}
        inflight.add(session_id)
        try:
            status = await teardown_session(
                session_id=session_id,
                info=info,
                launcher=launcher,
                registry=registry,
                lease=lease,
                store=store,
                http=_agent_http_or_pool(info, request),
                retain=retain,
            )
        finally:
            inflight.discard(session_id)
        if status == "stop_pending":
            return JSONResponse(
                status_code=int(HTTPStatus.ACCEPTED),
                content={"status": status},
            )
        return {"status": status}

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
            http=_agent_http_or_pool(info, request),
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
                    client=_agent_http(info),
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
            http=_agent_http_or_pool(info, request),
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
        if info.state != "live":
            msg = f"session {session_id} is {info.state}"
            raise SessionNotLive(
                msg,
                session_id=session_id,
                state=info.state,
                diagnostics=f"/sessions/{session_id}/diagnostics",
            )
        normalised = posixpath.normpath(f"/{path}").strip("/")
        if normalised in _LIFECYCLE_PATHS and request.method not in ("GET", "HEAD"):
            msg = (
                f"{request.method} /{normalised} is managed by the control plane;"
                " use POST /sessions or DELETE /sessions/{session_id}"
            )
            raise ManagedByControl(msg, session_id=session_id)
        registry.touch(session_id)
        return await proxy_request(
            request,
            info.agent_url,
            path,
            client=_agent_http(info),
            session_id=session_id,
        )

    return app
