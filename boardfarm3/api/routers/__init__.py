"""Router helpers shared across all boardfarm API router modules."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, TypeVar

from fastapi import HTTPException

if TYPE_CHECKING:
    from fastapi import APIRouter

    from boardfarm3.api.session import Session

T = TypeVar("T")

_ENTRYPOINT_GROUP = "boardfarm_api"


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
    if index >= len(devices):
        raise HTTPException(
            status_code=int(HTTPStatus.NOT_FOUND),
            detail=f"no {template.__name__} device at index {index}",
        )
    return devices[index]


def load_plugin_routers() -> list[APIRouter]:
    """Discover all FastAPI routers contributed via the ``boardfarm_api`` entrypoints.

    Creates a short-lived PluginManager, loads all installed ``boardfarm_api``
    entrypoints, and collects their routers.  Returns an empty list on any
    error so a missing or broken plugin does not crash the agent.

    :return: all contributed routers, in discovery order
    :rtype: list[APIRouter]
    """
    try:
        import pluggy

        from boardfarm3.api import hookspecs as _api_hookspecs

        _pm = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        _pm.add_hookspecs(_api_hookspecs)
        _pm.load_setuptools_entrypoints(_ENTRYPOINT_GROUP)
        results: list[list[APIRouter]] = _pm.hook.boardfarm_add_api_routers()
        return [router for routers in results for router in routers]
    except Exception:  # noqa: BLE001
        return []
