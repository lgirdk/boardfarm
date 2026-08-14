"""Plugin route discovery and unified OpenAPI wrapper registration."""

from __future__ import annotations

import inspect
import typing
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

if TYPE_CHECKING:
    from fastapi import FastAPI

    from boardfarm3_control.registry import SessionRegistry

_ENTRYPOINT_GROUP = "boardfarm_api"
_HOOKSPEC_MODULE = "boardfarm3.api.hookspecs"
_HOOK_NAME = "boardfarm_add_api_routers"


def load_plugin_routers() -> list[APIRouter]:
    """Discover routers from all ``boardfarm_api`` entrypoints.

    :return: all APIRouter objects contributed by installed plugins
    :rtype: list[APIRouter]
    """
    try:
        import pluggy

        from boardfarm3.api import hookspecs as api_hookspecs

        pm = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        pm.add_hookspecs(api_hookspecs)
        pm.load_setuptools_entrypoints(_ENTRYPOINT_GROUP)
        results: list[list[APIRouter]] = pm.hook.boardfarm_add_api_routers()
        return [router for routers in results for router in routers]
    except Exception:  # noqa: BLE001
        return []


def _make_proxy_endpoint(
    original_path: str,
    original_endpoint: Any,  # noqa: ANN401
    registry: SessionRegistry,
) -> Any:  # noqa: ANN401
    """Return a proxy handler that preserves the original endpoint's signature.

    FastAPI reads ``__signature__`` via ``inspect.signature()`` to generate the
    OpenAPI schema.  The wrapper has the same signature as ``original_endpoint``
    with ``session_id: str`` prepended and ``request: Request`` ensured present.
    At runtime it only reads ``session_id`` and ``request`` — the body is forwarded
    as raw bytes, never deserialised through Pydantic by the wrapper.

    :param original_path: plugin route path (without session prefix)
    :type original_path: str
    :param original_endpoint: the plugin's async handler function
    :type original_endpoint: Any
    :param registry: registry used to resolve the agent URL
    :type registry: SessionRegistry
    :return: proxy async function with adjusted signature
    :rtype: Any
    """
    from boardfarm3_control.proxy import proxy_request

    # Resolve ForwardRef annotations so Pydantic can build schemas correctly.
    # This matters when the caller module uses `from __future__ import annotations`.
    try:
        resolved_hints = typing.get_type_hints(original_endpoint)
    except Exception:  # noqa: BLE001
        resolved_hints = {}

    sig = inspect.signature(original_endpoint)
    existing_params = [
        p.replace(annotation=resolved_hints[p.name])
        if p.name in resolved_hints and p.annotation is not inspect.Parameter.empty
        else p
        for p in sig.parameters.values()
    ]

    # Build the new parameter list: session_id first, then request (if absent), then original params.
    new_params: list[inspect.Parameter] = [
        inspect.Parameter(
            "session_id",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=str,
        ),
    ]
    if not any(p.name == "request" for p in existing_params):
        new_params.append(
            inspect.Parameter(
                "request",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Request,
            ),
        )
    new_params.extend(existing_params)
    new_sig = sig.replace(parameters=new_params)

    clean_path = original_path.lstrip("/")

    async def proxy_endpoint(**kwargs: Any) -> Any:  # noqa: ANN401
        session_id: str = kwargs["session_id"]
        request: Request = kwargs["request"]
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(status_code=404, detail=f"unknown session {session_id}")
        return await proxy_request(request, info.agent_url, clean_path)

    proxy_endpoint.__signature__ = new_sig  # type: ignore[attr-defined]
    proxy_endpoint.__name__ = f"proxy_{original_endpoint.__name__}"
    proxy_endpoint.__doc__ = original_endpoint.__doc__
    return proxy_endpoint


def register_plugin_routes(
    app: FastAPI,
    routers: list[APIRouter],
    registry: SessionRegistry,
) -> None:
    """Wrap plugin routes as proxy-dispatch endpoints under ``/sessions/{session_id}/``.

    Each wrapped route preserves the original Pydantic request/response models
    so FastAPI generates an accurate unified OpenAPI schema.

    :param app: FastAPI application to register routes on
    :type app: FastAPI
    :param routers: plugin APIRouter objects from ``load_plugin_routers()``
    :type routers: list[APIRouter]
    :param registry: session registry used to resolve agent URLs at request time
    :type registry: SessionRegistry
    """
    for router in routers:
        wrapper_router = APIRouter()
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            new_path = f"/sessions/{{session_id}}/{route.path.lstrip('/')}"
            endpoint = _make_proxy_endpoint(route.path, route.endpoint, registry)
            wrapper_router.add_api_route(
                path=new_path,
                endpoint=endpoint,
                methods=list(route.methods or {"GET"}),
                response_model=route.response_model,
                tags=list(route.tags) if route.tags else None,
                summary=route.summary,
                description=route.description,
            )
        app.include_router(wrapper_router)
