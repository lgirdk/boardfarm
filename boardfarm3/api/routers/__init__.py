"""Router helpers shared across all boardfarm API router modules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, TypeVar

import pluggy
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from boardfarm3.api.execution import Job
    from boardfarm3.api.routers._generator import SkippedMethod
    from boardfarm3.api.session import Session

T = TypeVar("T")

_ENTRYPOINT_GROUP = "boardfarm_api"
_log = logging.getLogger(__name__)


@dataclass
class RouterBundle:
    """A namespace-prefixed group of FastAPI routers contributed by one plugin.

    :param namespace: URL namespace for this plugin's routes, e.g. ``"core"``
        or ``"docsis"``
    :type namespace: str
    :param routers: routers whose paths will be prefixed with
        ``/{namespace}``
    :type routers: list[APIRouter]
    :param skipped: methods the generator could not route for this bundle
    :type skipped: list[SkippedMethod]
    """

    namespace: str
    routers: list[APIRouter] = field(default_factory=list)
    skipped: list[SkippedMethod] = field(default_factory=list)


def _resolve(session: Session, template: type[T], index: int) -> T:
    """Return the device of *template* type at *index* from the session.

    :param session: active session whose device manager to query
    :type session: Session
    :param template: Template ABC to resolve against
    :type template: type[T]
    :param index: zero-based position in registration order
    :type index: int
    :return: resolved device instance
    :rtype: T
    :raises HTTPException: 409 when the session is not booted;
        404 when no device of the requested type exists at *index*
    """
    if session.runtime.device_manager is None:
        raise HTTPException(
            status_code=int(HTTPStatus.CONFLICT),
            detail="session is not booted — device_manager unavailable",
        )
    devices = list(
        session.runtime.device_manager.get_devices_by_type(template).values()
    )
    if index < 0 or index >= len(devices):
        raise HTTPException(
            status_code=int(HTTPStatus.NOT_FOUND),
            detail=f"no {template.__name__} device at index {index}",
        )
    return devices[index]


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


def _make_wrapper(bundle: RouterBundle) -> APIRouter:
    """Wrap bundle routers under the bundle namespace prefix.

    :param bundle: router bundle with namespace and routers
    :type bundle: RouterBundle
    :return: wrapper APIRouter with namespace prefix applied
    :rtype: APIRouter
    """
    wrapper = APIRouter(prefix=f"/{bundle.namespace}")
    for router in bundle.routers:
        wrapper.include_router(router)
    return wrapper


def load_plugin_routers() -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Discover all FastAPI routers contributed via the ``boardfarm_api`` entrypoints.

    Creates a short-lived PluginManager, loads all installed ``boardfarm_api``
    entrypoints, wraps each bundle's routers under ``/{bundle.namespace}``,
    and aggregates the skipped method lists from all bundles.

    :return: namespaced routers and all skipped methods from all bundles
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
    result_routers: list[APIRouter] = []
    result_skipped: list[SkippedMethod] = []
    try:
        from boardfarm3.api import hookspecs as _api_hookspecs  # pylint: disable=import-outside-toplevel

        _pm = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        _pm.add_hookspecs(_api_hookspecs)
        _pm.load_setuptools_entrypoints(_ENTRYPOINT_GROUP)
        bundles: list[list[RouterBundle]] = _pm.hook.boardfarm_add_api_routers()
        for bundle_list in bundles:
            for bundle in bundle_list:
                result_routers.append(_make_wrapper(bundle))
                result_skipped.extend(bundle.skipped)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return [], []
    return result_routers, result_skipped
