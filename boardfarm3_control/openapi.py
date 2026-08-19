"""Plugin route discovery and unified OpenAPI wrapper registration."""

from __future__ import annotations

import inspect
import json as _json
import typing
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute
from pydantic import create_model
from starlette.requests import Request

if TYPE_CHECKING:
    from fastapi import FastAPI

    from boardfarm3.api.routers import RouterBundle
    from boardfarm3_control.registry import SessionRegistry

_ENTRYPOINT_GROUP = "boardfarm_api"
_HOOKSPEC_MODULE = "boardfarm3.api.hookspecs"
_HOOK_NAME = "boardfarm_add_api_routers"


def _flatten_bundle(bundle: RouterBundle) -> APIRouter:
    """Build a single flat APIRouter from a :class:`RouterBundle`.

    Iterates each inner router's routes directly (rather than calling
    ``include_router``) so that FastAPI version-dependent prefix behaviour
    does not affect path construction.  The resulting router has no prefix
    of its own; every route's path is fully qualified:
    ``/{namespace}{inner_prefix}{relative}``.

    :param bundle: router bundle to flatten
    :type bundle: RouterBundle
    :return: flat APIRouter with all routes at their fully-qualified paths
    :rtype: APIRouter
    """
    flat = APIRouter()
    for inner in bundle.routers:
        inner_pfx: str = getattr(inner, "prefix", "") or ""
        for route in inner.routes:
            if not isinstance(route, APIRoute):
                continue
            # route.path may or may not include inner_pfx depending on
            # FastAPI version; removeprefix is safe for both cases.
            rel = route.path.removeprefix(inner_pfx)
            flat.add_api_route(
                f"/{bundle.namespace}{inner_pfx}{rel}",
                route.endpoint,
                methods=list(route.methods or {"POST"}),
                response_model=route.response_model,
                tags=list(route.tags) if route.tags else None,
                summary=route.summary,
                description=route.description,
                status_code=route.status_code,
            )
    return flat


def load_plugin_routers() -> list[APIRouter]:
    """Discover routers from all ``boardfarm_api`` entrypoints.

    Each :class:`~boardfarm3.api.routers.RouterBundle` is flattened into a
    single ``APIRouter`` whose routes carry fully-qualified paths that include
    both the bundle namespace and the inner router prefix
    (e.g. ``/core/templates/lan/ping``).

    :return: flattened APIRouter objects contributed by installed plugins
    :rtype: list[APIRouter]
    """
    result: list[APIRouter] = []
    try:
        import pluggy

        from boardfarm3.api import hookspecs as api_hookspecs

        pm = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        pm.add_hookspecs(api_hookspecs)
        pm.load_setuptools_entrypoints(_ENTRYPOINT_GROUP)
        bundle_lists: list[list[RouterBundle]] = pm.hook.boardfarm_add_api_routers()
        result.extend(
            _flatten_bundle(bundle)
            for bundle_list in bundle_lists
            for bundle in bundle_list
        )
    except Exception:  # noqa: BLE001
        return []
    return result


def _make_proxy_endpoint(
    original_endpoint: Any,  # noqa: ANN401
    registry: SessionRegistry,
) -> Any:  # noqa: ANN401
    """Return a proxy handler that preserves the original endpoint's signature.

    FastAPI reads ``__signature__`` via ``inspect.signature()`` to generate the
    OpenAPI schema.  The wrapper has the same signature as ``original_endpoint``
    with ``session_id: str`` injected into the Pydantic body model and
    ``request: Request`` ensured present.  At runtime the proxy extracts
    ``session_id`` from the body, strips it, and forwards the remainder to the
    downstream agent.

    .. note::
        The endpoint's body parameter **must** be named ``body`` (not ``_body`` or
        any other name) for ``session_id`` injection to take effect.  An endpoint
        whose body parameter has a different name will compile without error but
        raise ``KeyError`` at call time.

    :param original_endpoint: the plugin's async handler function
    :type original_endpoint: Any
    :param registry: registry used to resolve the agent URL
    :type registry: SessionRegistry
    :return: proxy async function with adjusted signature
    :rtype: Any
    """
    from boardfarm3_control.proxy import proxy_request

    try:
        resolved_hints = typing.get_type_hints(original_endpoint)
    except Exception:  # noqa: BLE001
        resolved_hints = {}

    sig = inspect.signature(original_endpoint)
    existing_params: list[inspect.Parameter] = [
        p.replace(annotation=resolved_hints[p.name])
        if p.name in resolved_hints and p.annotation is not inspect.Parameter.empty
        else p
        for p in sig.parameters.values()
    ]

    # Extend the Pydantic body model with a required session_id field.
    body_idx = next(
        (i for i, p in enumerate(existing_params) if p.name == "body"),
        None,
    )
    if body_idx is not None:
        original_model = existing_params[body_idx].annotation
        if hasattr(original_model, "model_fields"):
            proxied_model = create_model(
                f"Proxied{original_model.__name__}",
                session_id=(str, ...),
                **{
                    name: (fi.annotation, fi)
                    for name, fi in original_model.model_fields.items()
                },
            )
            existing_params[body_idx] = existing_params[body_idx].replace(
                annotation=proxied_model
            )

    # Ensure request is present; do not add a separate session_id path param.
    new_params: list[inspect.Parameter] = []
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

    async def proxy_endpoint(**kwargs: Any) -> Any:  # noqa: ANN401
        body: Any = kwargs["body"]  # noqa: ANN401
        request: Request = kwargs["request"]
        session_id: str = body.session_id
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(status_code=404, detail=f"unknown session {session_id}")
        stripped = body.model_dump(exclude={"session_id"})
        stripped_bytes = _json.dumps(stripped).encode()
        downstream_path = request.url.path.lstrip("/")
        return await proxy_request(
            request, info.agent_url, downstream_path, body=stripped_bytes
        )

    proxy_endpoint.__signature__ = new_sig  # type: ignore[attr-defined]
    proxy_endpoint.__name__ = f"proxy_{original_endpoint.__name__}"
    proxy_endpoint.__doc__ = original_endpoint.__doc__
    return proxy_endpoint


def register_plugin_routes(
    app: FastAPI,
    routers: list[APIRouter],
    registry: SessionRegistry,
) -> None:
    """Wrap plugin routes as proxy-dispatch endpoints, injecting ``session_id`` into each body model.

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
            new_path = f"/{route.path.lstrip('/')}"
            endpoint = _make_proxy_endpoint(route.endpoint, registry)
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
