"""Runtime template router generator for boardfarm API.

Introspects Template ABCs at agent startup and builds FastAPI routes
for all public methods with JSON-serialisable signatures.
"""

from __future__ import annotations

import inspect
import logging
import types
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Literal, Union, get_args, get_origin

from fastapi import APIRouter, Request
from pydantic import create_model

from boardfarm3.api.routers import _async_response, _resolve

if TYPE_CHECKING:
    from fastapi.responses import JSONResponse

_log = logging.getLogger(__name__)

# Guard for the Python 3.10+ union syntax type (X | Y).
_UNION_TYPE: type | None = getattr(types, "UnionType", None)  # pylint: disable=invalid-name

# Primitive types that are directly JSON-serialisable.
_PRIMITIVE_TYPES: frozenset[type] = frozenset({str, int, float, bool, dict, list})

# NoneType singleton — avoids calling type() at check time (pylint C0123).
_NONE_TYPE: type = type(None)  # pylint: disable=invalid-name

# ---------------------------------------------------------------------------
# Serialisability check
# ---------------------------------------------------------------------------


def _is_serialisable(annotation: Any) -> bool:  # noqa: ANN401
    """Return True if *annotation* is JSON-serialisable.

    :param annotation: a type annotation to check
    :type annotation: Any
    :return: True when the type can be expressed as JSON
    :rtype: bool
    """
    # None / NoneType (-> None annotation), typing.Any, and bare primitives
    if (
        annotation is None
        or annotation is _NONE_TYPE
        or annotation is Any
        or annotation in _PRIMITIVE_TYPES
    ):
        return True
    origin = get_origin(annotation)
    # Union types (both X | Y syntax and Union[X, Y]) and generic dict/list:
    # all share the same "recurse into args" logic.
    is_union = (
        _UNION_TYPE is not None and isinstance(annotation, _UNION_TYPE)
    ) or origin is Union
    if is_union or origin in (dict, list):
        return all(_is_serialisable(a) for a in get_args(annotation))
    return False


# ---------------------------------------------------------------------------
# SkippedMethod
# ---------------------------------------------------------------------------


@dataclass
class SkippedMethod:
    """A template method excluded from route generation.

    :param template: name of the template ABC
    :type template: str
    :param method: method name
    :type method: str
    :param reason: human-readable skip reason
    :type reason: str
    """

    template: str
    method: str
    reason: str


@dataclass
class TemplateMount:
    """Describes how a template's methods mount as routes.

    :param mount: URL segment under ``/templates/`` (e.g. ``"cpe"``)
    :type mount: str
    :param resolve_as: template type looked up in the device manager
    :type resolve_as: type
    :param introspect: template ABC whose methods become routes
    :type introspect: type
    :param accessor: attribute on the resolved device to dispatch through
        (``"sw"`` / ``"hw"``); ``None`` dispatches on the device itself
    :type accessor: str | None
    """

    mount: str
    resolve_as: type
    introspect: type
    accessor: str | None = None


def _normalise_mount(item: type | TemplateMount) -> TemplateMount:
    """Return *item* as a TemplateMount, wrapping a bare template type.

    :param item: a template class or an explicit TemplateMount
    :type item: type | TemplateMount
    :return: a TemplateMount describing how to mount the template
    :rtype: TemplateMount
    """
    if isinstance(item, TemplateMount):
        return item
    return TemplateMount(item.__name__.lower(), item, item, None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_request_model(method_name: str, sig: inspect.Signature) -> type:
    """Build a Pydantic model from the non-self parameters of *sig*.

    :param method_name: used to derive the model class name
    :type method_name: str
    :param sig: method signature (``self`` is excluded by the caller)
    :type sig: inspect.Signature
    :return: dynamically created Pydantic BaseModel subclass
    :rtype: type
    """
    fields: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        annotation = param.annotation
        default = param.default if param.default is not inspect.Parameter.empty else ...
        fields[name] = (annotation, default)
    model_name = (
        "".join(part.capitalize() for part in method_name.split("_")) + "Request"
    )
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def _make_handler(
    resolve_as: type,
    introspect: type,
    method_name: str,
    request_model: type,
    accessor: str | None,
) -> Any:  # noqa: ANN401
    """Build an async route handler for *method_name*.

    Injects ``__signature__`` so FastAPI generates a correct OpenAPI schema
    for the dynamically created function.

    :param resolve_as: template type resolved from the device manager
    :type resolve_as: type
    :param introspect: template whose method is dispatched
    :type introspect: type
    :param method_name: name of the method to dispatch
    :type method_name: str
    :param request_model: Pydantic model for the request body
    :type request_model: type
    :param accessor: attribute to dispatch through, or None for the device
    :type accessor: str | None
    :return: async FastAPI route handler
    :rtype: Any
    """

    async def handler(
        request: Request,
        body: Any,  # noqa: ANN401
        index: int = 0,
        mode: str = "sync",
    ) -> dict[str, Any] | JSONResponse:
        session = request.app.state.session
        device: Any = _resolve(  # type: ignore[type-abstract]
            session, resolve_as, index
        )
        target = device if accessor is None else getattr(device, accessor)
        job = await session.queue.submit(
            lambda: getattr(target, method_name)(**body.model_dump()),
            mode=mode,
        )
        if mode == "async":
            return _async_response(job)
        return {"result": job.result}

    handler.__name__ = f"{introspect.__name__.lower()}_{method_name}"
    handler.__qualname__ = handler.__name__
    handler.__doc__ = (
        f"{method_name.replace('_', ' ').capitalize()} on"
        f" {introspect.__name__} device at *index*."
    )
    handler.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter(
                "request",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Request,
            ),
            inspect.Parameter(
                "body",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=request_model,
            ),
            inspect.Parameter(
                "index",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=0,
                annotation=int,
            ),
            inspect.Parameter(
                "mode",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default="sync",
                annotation=Literal["sync", "async"],
            ),
        ]
    )
    return handler


def _validate_sig(  # pylint: disable=too-many-return-statements
    template_name: str,
    name: str,
    sig: inspect.Signature,
) -> SkippedMethod | None:
    """Check a method signature for skip conditions.

    :param template_name: class name used in SkippedMethod records
    :type template_name: str
    :param name: method name
    :type name: str
    :param sig: already-resolved method signature
    :type sig: inspect.Signature
    :return: SkippedMethod if any condition requires skipping, else None
    :rtype: SkippedMethod | None
    """
    has_var = any(
        p.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        for p in sig.parameters.values()
    )
    if has_var:
        return SkippedMethod(template_name, name, "has *args or **kwargs")

    missing = [
        p_name
        for p_name, p in sig.parameters.items()
        if p_name != "self" and p.annotation is inspect.Parameter.empty
    ]
    if missing:
        return SkippedMethod(
            template_name, name, f"missing annotation on: {', '.join(missing)}"
        )

    ret = sig.return_annotation
    if ret is inspect.Parameter.empty:
        return SkippedMethod(template_name, name, "missing return annotation")
    if not _is_serialisable(ret):
        return SkippedMethod(
            template_name, name, f"non-serialisable return type: {ret!r}"
        )

    return None


def _process_member(  # pylint: disable=too-many-return-statements
    introspect: type,
    name: str,
    obj: object,
) -> SkippedMethod | type | None:
    """Process a single class member to determine route generation outcome.

    :param introspect: Template ABC class being introspected
    :type introspect: type
    :param name: attribute name from ``inspect.getmembers``
    :type name: str
    :param obj: attribute value (result of ``getattr(introspect, name)``)
    :type obj: object
    :return: a Pydantic request model to register a route for, a
        SkippedMethod, or None to skip silently
    :rtype: SkippedMethod | type | None
    """
    raw = inspect.getattr_static(introspect, name, None)

    if isinstance(raw, (property, cached_property)):
        return SkippedMethod(introspect.__name__, name, "property")
    if not callable(obj) or isinstance(raw, (classmethod, staticmethod)):
        return None

    try:
        sig = inspect.signature(obj, eval_str=True)  # type: ignore[call-arg]
    except (ValueError, TypeError):
        return None
    except NameError:
        return SkippedMethod(introspect.__name__, name, "unevaluable annotation")

    skipped = _validate_sig(introspect.__name__, name, sig)
    if skipped is not None:
        return skipped

    return _make_request_model(name, sig)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class _MountBuild:
    """Mutable state accumulated while building one mount's router.

    :param mount: URL segment this router mounts under
    :type mount: str
    :param router: router being built for *mount*
    :type router: APIRouter
    :param seen: method names already registered for *mount*
    :type seen: set[str]
    :param all_skipped: shared list of skipped methods to append to
    :type all_skipped: list[SkippedMethod]
    """

    mount: str
    router: APIRouter
    seen: set[str]
    all_skipped: list[SkippedMethod]


def _register_member(  # pylint: disable=too-many-return-statements
    build: _MountBuild,
    spec: TemplateMount,
    name: str,
    obj: object,
) -> None:
    """Process one introspected member and register its route, if accepted.

    Mutates *build* in place: on acceptance the handler is registered on
    ``build.router`` and *name* is added to ``build.seen``; on rejection a
    :class:`SkippedMethod` is appended to ``build.all_skipped`` (dunder
    members are skipped silently).

    :param build: mutable build state for the mount *name* belongs to
    :type build: _MountBuild
    :param spec: mount spec that *name* was introspected from
    :type spec: TemplateMount
    :param name: attribute name from ``inspect.getmembers``
    :type name: str
    :param obj: attribute value (result of ``getattr(spec.introspect, name)``)
    :type obj: object
    :return: None
    :rtype: None
    """
    if name.startswith("__"):
        return
    if name.startswith("_"):
        build.all_skipped.append(
            SkippedMethod(spec.introspect.__name__, name, "private")
        )
        _log.warning(
            "template route skipped: %s.%s — private",
            spec.introspect.__name__,
            name,
        )
        return
    if name in build.seen:
        build.all_skipped.append(
            SkippedMethod(
                spec.introspect.__name__, name, f"duplicate in mount '{build.mount}'"
            )
        )
        return

    result = _process_member(spec.introspect, name, obj)
    if result is None:
        return
    if isinstance(result, SkippedMethod):
        build.all_skipped.append(result)
        _log.warning(
            "template route skipped: %s.%s — %s",
            spec.introspect.__name__,
            result.method,
            result.reason,
        )
        return

    request_model = result
    handler = _make_handler(
        spec.resolve_as, spec.introspect, name, request_model, spec.accessor
    )
    build.seen.add(name)
    router = build.router
    router.post(f"/{name}", status_code=200, response_model=None)(handler)
    router.post(f"/{{index}}/{name}", status_code=200, response_model=None)(handler)


def generate_template_routers(
    templates: list[type | TemplateMount],
) -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Generate FastAPI routers for each template mount.

    Bare template types are treated as a single-source mount. Multiple
    ``TemplateMount`` specs sharing a ``mount`` flatten into one router; a
    method name contributed by more than one spec is kept from the first
    spec only and the rest are skipped.

    :param templates: template classes or TemplateMount specs to introspect
    :type templates: list[type | TemplateMount]
    :return: generated routers and list of skipped methods with reasons
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
    mounts = [_normalise_mount(t) for t in templates]
    grouped: dict[str, list[TemplateMount]] = {}
    order: list[str] = []
    for spec in mounts:
        if spec.mount not in grouped:
            grouped[spec.mount] = []
            order.append(spec.mount)
        grouped[spec.mount].append(spec)

    routers: list[APIRouter] = []
    all_skipped: list[SkippedMethod] = []

    for mount in order:
        router = APIRouter(
            prefix=f"/templates/{mount}",
            tags=[f"templates:{mount}"],
        )
        build = _MountBuild(mount, router, set(), all_skipped)
        for spec in grouped[mount]:
            for name, obj in inspect.getmembers(spec.introspect):
                _register_member(build, spec, name, obj)

        routers.append(router)

    return routers, all_skipped
