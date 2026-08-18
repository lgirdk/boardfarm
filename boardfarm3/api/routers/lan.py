"""FastAPI router for the LAN device template."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from boardfarm3.api.routers import _resolve
from boardfarm3.templates.lan import LAN

if TYPE_CHECKING:
    from boardfarm3.api.execution import Job

router = APIRouter(prefix="/templates/lan", tags=["templates:lan"])


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class LanPingRequest(BaseModel):
    """Request body for the LAN ``ping`` route."""

    ping_ip: str
    ping_count: int = 4
    ping_interface: str | None = None
    options: str = ""
    timeout: int = 50
    json_output: bool = False


class LanGetInterfaceMacaddrRequest(BaseModel):
    """Request body for the LAN ``get_interface_macaddr`` route."""

    interface: str


class LanGetInterfaceIpv4addrRequest(BaseModel):
    """Request body for the LAN ``get_interface_ipv4addr`` route."""

    interface: str


class LanSetLinkStateRequest(BaseModel):
    """Request body for the LAN ``set_link_state`` route."""

    interface: str
    state: str


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post("/ping", status_code=int(HTTPStatus.OK), response_model=None)
@router.post("/{index}/ping", status_code=int(HTTPStatus.OK), response_model=None)
async def lan_ping(
    request: Request,
    body: LanPingRequest,
    index: int = 0,
    mode: Literal["sync", "async"] = "sync",
) -> dict[str, Any] | JSONResponse:
    """Ping a remote host from the LAN device at *index*.

    :param request: incoming HTTP request; provides the session via
        ``request.app.state.session``
    :type request: Request
    :param body: ping parameters
    :type body: LanPingRequest
    :param index: zero-based LAN device index, defaults to 0
    :type index: int
    :param mode: ``"sync"`` blocks until done and returns the result;
        ``"async"`` enqueues immediately and returns a job ticket
    :type mode: Literal["sync", "async"]
    :return: ``{"result": bool | dict}`` in sync mode;
        ``{"job_id": str, "state": str}`` with HTTP 202 in async mode
    :rtype: dict[str, Any] | JSONResponse
    """
    session = request.app.state.session
    device = _resolve(session, LAN, index)  # type: ignore[type-abstract]
    job = await session.queue.submit(
        lambda: device.ping(**body.model_dump()),
        mode=mode,
    )
    if mode == "async":
        return _async_response(job)
    return {"result": job.result}


@router.post(
    "/get_interface_macaddr", status_code=int(HTTPStatus.OK), response_model=None
)
@router.post(
    "/{index}/get_interface_macaddr",
    status_code=int(HTTPStatus.OK),
    response_model=None,
)
async def lan_get_interface_macaddr(
    request: Request,
    body: LanGetInterfaceMacaddrRequest,
    index: int = 0,
    mode: Literal["sync", "async"] = "sync",
) -> dict[str, Any] | JSONResponse:
    """Get the MAC address of a network interface on the LAN device at *index*.

    :param request: incoming HTTP request
    :type request: Request
    :param body: interface name
    :type body: LanGetInterfaceMacaddrRequest
    :param index: zero-based LAN device index, defaults to 0
    :type index: int
    :param mode: execution mode; ``"sync"`` or ``"async"``
    :type mode: Literal["sync", "async"]
    :return: ``{"result": str}`` in sync mode;
        ``{"job_id": str, "state": str}`` with HTTP 202 in async mode
    :rtype: dict[str, Any] | JSONResponse
    """
    session = request.app.state.session
    device = _resolve(session, LAN, index)  # type: ignore[type-abstract]
    job = await session.queue.submit(
        lambda: device.get_interface_macaddr(body.interface),
        mode=mode,
    )
    if mode == "async":
        return _async_response(job)
    return {"result": job.result}


@router.post(
    "/get_interface_ipv4addr", status_code=int(HTTPStatus.OK), response_model=None
)
@router.post(
    "/{index}/get_interface_ipv4addr",
    status_code=int(HTTPStatus.OK),
    response_model=None,
)
async def lan_get_interface_ipv4addr(
    request: Request,
    body: LanGetInterfaceIpv4addrRequest,
    index: int = 0,
    mode: Literal["sync", "async"] = "sync",
) -> dict[str, Any] | JSONResponse:
    """Get the IPv4 address of a network interface on the LAN device at *index*.

    :param request: incoming HTTP request
    :type request: Request
    :param body: interface name
    :type body: LanGetInterfaceIpv4addrRequest
    :param index: zero-based LAN device index, defaults to 0
    :type index: int
    :param mode: execution mode; ``"sync"`` or ``"async"``
    :type mode: Literal["sync", "async"]
    :return: ``{"result": str}`` in sync mode;
        ``{"job_id": str, "state": str}`` with HTTP 202 in async mode
    :rtype: dict[str, Any] | JSONResponse
    """
    session = request.app.state.session
    device = _resolve(session, LAN, index)  # type: ignore[type-abstract]
    job = await session.queue.submit(
        lambda: device.get_interface_ipv4addr(body.interface),
        mode=mode,
    )
    if mode == "async":
        return _async_response(job)
    return {"result": job.result}


@router.post("/set_link_state", status_code=int(HTTPStatus.OK), response_model=None)
@router.post(
    "/{index}/set_link_state", status_code=int(HTTPStatus.OK), response_model=None
)
async def lan_set_link_state(
    request: Request,
    body: LanSetLinkStateRequest,
    index: int = 0,
    mode: Literal["sync", "async"] = "sync",
) -> dict[str, Any] | JSONResponse:
    """Set the link state of a network interface on the LAN device at *index*.

    :param request: incoming HTTP request
    :type request: Request
    :param body: interface name and desired link state
    :type body: LanSetLinkStateRequest
    :param index: zero-based LAN device index, defaults to 0
    :type index: int
    :param mode: execution mode; ``"sync"`` or ``"async"``
    :type mode: Literal["sync", "async"]
    :return: ``{"result": None}`` in sync mode;
        ``{"job_id": str, "state": str}`` with HTTP 202 in async mode
    :rtype: dict[str, Any] | JSONResponse
    """
    session = request.app.state.session
    device = _resolve(session, LAN, index)  # type: ignore[type-abstract]
    job = await session.queue.submit(
        lambda: device.set_link_state(body.interface, body.state),
        mode=mode,
    )
    if mode == "async":
        return _async_response(job)
    return {"result": job.result}


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _async_response(job: Job) -> JSONResponse:
    """Build a 202 Accepted JSON response from a queued *job*.

    The route decorator's ``status_code`` only applies to non-``Response``
    return values.  Async handlers therefore return an explicit
    ``JSONResponse`` to emit HTTP 202 rather than the route's 200.

    :param job: the job returned by ``queue.submit(..., mode="async")``
    :type job: Job
    :return: 202 response carrying ``job_id`` and the current job state
    :rtype: JSONResponse
    """
    return JSONResponse(
        status_code=int(HTTPStatus.ACCEPTED),
        content={"job_id": job.id, "state": job.state.value},
    )
