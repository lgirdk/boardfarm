"""Plugin route discovery and unified OpenAPI wrapper registration."""

from __future__ import annotations

import inspect
import logging
import typing
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute
from pydantic import create_model
from starlette.requests import Request

from boardfarm3_control.proxy import proxy_request

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from boardfarm3.api.routers import RouterBundle
    from boardfarm3_control.registry import SessionRegistry

_log = logging.getLogger(__name__)

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
            if bundle.error_shaper is not None:
                route.endpoint.__bf_error_shaper__ = bundle.error_shaper  # type: ignore[attr-defined]  # pylint: disable=line-too-long
            if bundle.optional_session_id:
                route.endpoint.__bf_optional_session_id__ = True  # type: ignore[attr-defined]
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

    A plugin that raises while building its routers is logged and skipped;
    the remaining plugins still contribute their routes.

    :return: flattened APIRouter objects contributed by installed plugins
    :rtype: list[APIRouter]
    """
    try:
        import pluggy

        from boardfarm3.api import hookspecs as api_hookspecs
        from boardfarm3.api.routers import iter_plugin_bundles

        pm = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        pm.add_hookspecs(api_hookspecs)
        pm.load_setuptools_entrypoints(_ENTRYPOINT_GROUP)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        _log.exception("failed to load %s entrypoints", _ENTRYPOINT_GROUP)
        return []

    return [_flatten_bundle(bundle) for bundle in iter_plugin_bundles(pm)]


async def _dispatch_proxy_request(
    kwargs: dict[str, Any],
    *,
    registry: SessionRegistry,
    shaper: Callable[[Exception], Any] | None,
) -> Any:  # noqa: ANN401
    """Resolve the session, forward to the agent, and shape dispatch-edge errors.

    Split out of :func:`_make_proxy_endpoint` so the control-plane dispatch
    edge (unknown session, missing ``session_id``) has its own complexity
    budget, separate from the signature-rewriting machinery around it.

    :param kwargs: the proxy endpoint's call-time keyword arguments; must
        contain ``body`` and ``request``
    :type kwargs: dict[str, Any]
    :param registry: registry used to resolve the agent URL
    :type registry: SessionRegistry
    :param shaper: converts a dispatch-edge exception into a response in the
        bundle's contract; None re-raises natively
    :type shaper: Callable[[Exception], Any] | None
    :return: the downstream response, or the shaper's response on failure
    :rtype: Any
    :raises Exception: whatever was raised, when *shaper* is None
    """
    try:
        body: Any = kwargs["body"]
        request: Request = kwargs["request"]
        session_id: str | None = body.session_id
        if session_id is None:
            raise HTTPException(  # noqa: TRY301
                status_code=422,
                detail="session_id is required",
            )
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(  # noqa: TRY301
                status_code=404, detail=f"unknown session {session_id}"
            )
        stripped_bytes = body.model_dump_json(exclude={"session_id"}).encode()
        downstream_path = request.url.path.lstrip("/")
        return await proxy_request(
            request, info.agent_url, downstream_path, body=stripped_bytes
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if shaper is None:
            raise
        return shaper(exc)


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
        raise ``KeyError`` at call time — unless the bundle supplies an
        ``error_shaper``, in which case the ``KeyError`` is caught and shaped
        like any other dispatch-edge failure (harder to diagnose).

    .. note::
        ``__bf_error_shaper__`` and ``__bf_optional_session_id__`` are read off
        *original_endpoint*.  They are stamped by ``_flatten_bundle`` from the
        owning :class:`~boardfarm3.api.routers.RouterBundle`; the channel exists
        as a plain function attribute (rather than being threaded through as a
        parameter) because ``create_app`` also accepts ``extra_routers`` that
        were never wrapped from a bundle and so carry no such metadata.

    :param original_endpoint: the plugin's async handler function
    :type original_endpoint: Any
    :param registry: registry used to resolve the agent URL
    :type registry: SessionRegistry
    :return: proxy async function with adjusted signature
    :rtype: Any
    """
    shaper = getattr(original_endpoint, "__bf_error_shaper__", None)
    optional_sid = getattr(original_endpoint, "__bf_optional_session_id__", False)

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
            session_id_spec = (str | None, None) if optional_sid else (str, ...)
            proxied_model = create_model(  # type: ignore[call-overload]
                f"Proxied{original_model.__name__}",
                session_id=session_id_spec,
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
        return await _dispatch_proxy_request(kwargs, registry=registry, shaper=shaper)

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
