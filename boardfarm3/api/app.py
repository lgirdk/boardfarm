"""FastAPI application for the boardfarm runtime agent."""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pexpect
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from boardfarm3.api.errors import console_tail_from, error_envelope, http_status_for
from boardfarm3.api.runtime import RuntimeOptions
from boardfarm3.api.session import Session, SessionState
from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm3.exceptions import BoardfarmException

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class ConfigOptions(BaseModel):
    """Runtime option overrides accepted by ``POST /session/config``.

    Fields mirror the settable fields of ``RuntimeOptions``. ``board_name``
    is intentionally excluded: it identifies which board this agent owns and
    is fixed at ``create_app()`` time, not something a config call should be
    able to move. ``extra="forbid"`` turns an unknown key into a visible
    ``422`` instead of the silent no-op that ``Session.configure()``'s
    ``hasattr``-guarded ``setattr`` would otherwise produce.
    """

    model_config = ConfigDict(extra="forbid")

    skip_boot: bool | None = None
    legacy: bool | None = None
    skip_contingency_checks: bool | None = None
    save_console_logs: str | None = None
    ignore_devices: str | None = None


class ConfigIn(BaseModel):
    """Body of ``POST /session/config``."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]
    options: ConfigOptions = Field(default_factory=ConfigOptions)


def build_session(session_id: str, options: RuntimeOptions) -> Session:
    """Build a session. Overridden in tests to inject a fake runtime.

    :param session_id: session identifier
    :type session_id: str
    :param options: runtime options
    :type options: RuntimeOptions
    :return: session
    :rtype: Session
    """
    return Session(session_id, options)


def create_app(  # noqa: C901, PLR0915  # pylint: disable=too-many-locals,too-many-statements
    session_id: str,
    board_name: str,
) -> FastAPI:
    """Build the runtime agent application for one session.

    :param session_id: session identifier assigned by the control plane
    :type session_id: str
    :param board_name: board this agent owns
    :type board_name: str
    :return: FastAPI application
    :rtype: FastAPI
    """
    state: dict[str, Any] = {}

    async def release_once() -> None:
        # Session.release() submits to the execution queue and then shuts
        # the queue down, so calling it twice raises RuntimeError from the
        # already-shutdown ThreadPoolExecutor. DELETE /session and lifespan
        # shutdown both call this helper, so whichever runs first wins and
        # the other is a no-op.
        if state.get("released"):
            return
        state["released"] = True
        await state["session"].release()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        session = build_session(session_id, RuntimeOptions(board_name=board_name))
        state["session"] = session
        state["released"] = False
        # Exposed on app.state (in addition to the closure above) purely as
        # an observability/testability seam -- nothing here reads it back.
        app.state.session = session
        yield
        await release_once()

    app = FastAPI(title=f"boardfarm runtime agent [{board_name}]", lifespan=lifespan)

    # Discover and mount plugin-contributed routers (template methods, use cases, etc.).
    # load_plugin_routers() uses a short-lived PluginManager for the boardfarm_api
    # entrypoint group — separate from the process-global boardfarm PluginManager.
    from boardfarm3.api.routers import load_plugin_routers

    for _router in load_plugin_routers():
        app.include_router(_router)

    def session() -> Session:
        return state["session"]

    # Handle BoardfarmException and pexpect errors specifically, NOT bare
    # Exception. Starlette's ServerErrorMiddleware re-raises after running an
    # `Exception` handler, so TestClient would see the exception instead of the
    # envelope. Narrower handlers run in ExceptionMiddleware and return cleanly.
    async def handle_boardfarm_error(_: Request, exc: Exception) -> JSONResponse:
        current = state.get("session")
        return JSONResponse(
            status_code=http_status_for(exc),
            content=error_envelope(
                exc,
                session_id=session_id,
                console_tail=(
                    console_tail_from(current.buffer, None) if current else ""
                ),
            ),
        )

    for exception_type in (BoardfarmException, pexpect.TIMEOUT, pexpect.EOF):
        app.add_exception_handler(exception_type, handle_boardfarm_error)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return session().status()

    @app.post("/session/config")
    async def configure(body: ConfigIn) -> dict[str, Any]:
        current = session()
        overrides = body.options.model_dump(exclude_none=True)
        await current.configure(body.payload, overrides)
        return current.status()

    @app.post("/session/boot", status_code=int(HTTPStatus.ACCEPTED))
    async def boot(mode: Literal["sync", "async"] = "sync") -> dict[str, Any]:
        current = session()
        if current.state is not SessionState.CONFIGURED:
            raise HTTPException(
                status_code=int(HTTPStatus.CONFLICT),
                detail=f"cannot boot from state {current.state.value}",
            )
        if mode == "async":
            # Fire-and-forget: keep a strong reference on `state` so the task
            # is not garbage-collected mid-boot, and consume its exception
            # (Session.boot() records failures on the session itself; it
            # should not raise here) so asyncio does not warn that it was
            # never retrieved.
            task = asyncio.create_task(current.boot())
            task.add_done_callback(
                lambda done: None if done.cancelled() else done.exception(),
            )
            state["boot_task"] = task
            # Yield to the event loop once so the task can run up to its first
            # suspension point (queue.submit with mode="async" is effectively
            # synchronous), ensuring _boot_job is set before status() is called.
            await asyncio.sleep(0)
        else:
            await current.boot()
        return current.status()

    @app.get("/session")
    async def status() -> dict[str, Any]:
        return session().status()

    @app.delete("/session")
    async def release() -> dict[str, str]:
        await release_once()
        return {"status": "released"}

    @app.get("/devices")
    async def devices() -> dict[str, Any]:
        current = session()
        if current.runtime.device_manager is None:
            return {"devices": []}
        found = current.runtime.device_manager.get_devices_by_type(BoardfarmDevice)
        return {
            "devices": [
                {
                    "name": name,
                    "type": type(device).__name__,
                    "templates": sorted(
                        base.__name__
                        for base in type(device).__mro__
                        if getattr(base, "__abstractmethods__", None)
                    ),
                }
                for name, device in found.items()
            ],
        }

    @app.get("/console")
    async def console(
        cursor: int = 0,
        device: str | None = None,
        stream: str | None = None,
        limit: int = 10_000,
    ) -> dict[str, Any]:
        events, next_cursor = session().buffer.read(
            cursor=cursor,
            device=device,
            stream=stream,
            limit=limit,
        )
        return {"events": [event.__dict__ for event in events], "cursor": next_cursor}

    @app.get("/console/stream")
    async def console_stream(
        request: Request,
        device: str | None = None,
        cursor: int = 0,
    ) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            buf = session().buffer
            async with buf.subscription() as queue:
                # Snapshot the head before reading history so events that
                # arrive between subscription and read are yielded exactly
                # once — from the live queue, not duplicated from history.
                live_from = buf.next_seq
                past, _ = buf.read(cursor=cursor, limit=50_000, device=device)
                for event in past:
                    if event.seq < live_from:
                        yield f"data: {json.dumps(event.__dict__)}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    if device is not None and event.device != device:
                        continue
                    yield f"data: {json.dumps(event.__dict__)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/console/archive")
    async def console_archive() -> Response:
        current = session()
        directory = current.options.save_console_logs
        if not directory or not Path(directory).is_dir():
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail="save_console_logs is not enabled for this session",
            )
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            archive.add(directory, arcname="console-logs")
        return Response(
            content=buffer.getvalue(),
            media_type="application/gzip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{session_id}-console-logs.tar.gz"'
                ),
            },
        )

    @app.get("/jobs/{job_id}")
    async def job(job_id: str) -> dict[str, Any]:
        found = session().queue.get(job_id)
        if found is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown job {job_id}",
            )
        return {
            "job_id": found.id,
            "state": found.state.value,
            "result": found.result,
            "error": (
                error_envelope(found.error, session_id=session_id, job_id=found.id)
                if found.error
                else None
            ),
        }

    @app.get("/jobs/{job_id}/console")
    async def job_console(job_id: str, cursor: int = 0) -> dict[str, Any]:
        events, next_cursor = session().buffer.read(cursor=cursor, job_id=job_id)
        return {"events": [event.__dict__ for event in events], "cursor": next_cursor}

    return app
