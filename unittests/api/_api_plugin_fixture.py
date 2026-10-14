"""A minimal boardfarm_api plugin, loaded through a fake entry point in tests."""

from __future__ import annotations

from fastapi import APIRouter
from pluggy import HookimplMarker

from boardfarm3.api.routers import RouterBundle

hookimpl_api = HookimplMarker("boardfarm_api")
_router = APIRouter()


@_router.post("/hello")
async def hello() -> dict[str, str]:
    """Answer.

    :return: a greeting
    :rtype: dict[str, str]
    """
    return {"result": "hi"}


@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:
    """Contribute one route under the ``good`` namespace.

    :return: one bundle
    :rtype: list[RouterBundle]
    """
    return [RouterBundle(namespace="good", routers=[_router])]
