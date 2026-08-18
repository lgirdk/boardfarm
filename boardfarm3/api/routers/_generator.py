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

if TYPE_CHECKING:
    from fastapi.responses import JSONResponse

from boardfarm3.api.routers import _async_response, _resolve

_log = logging.getLogger(__name__)

# Guard for the Python 3.10+ union syntax type (X | Y).
_UNION_TYPE: type | None = getattr(types, "UnionType", None)

# Primitive types that are directly JSON-serialisable.
_PRIMITIVE_TYPES: frozenset[type] = frozenset({str, int, float, bool, dict, list})

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
    if annotation is None or annotation is type(None) or annotation is Any:
        return True
    if annotation in _PRIMITIVE_TYPES:
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
        default = (
            param.default if param.default is not inspect.Parameter.empty else ...
        )
        fields[name] = (annotation, default)
    model_name = (
        "".join(part.capitalize() for part in method_name.split("_")) + "Request"
    )
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def _make_handler(
    template: type,
    method_name: str,
    request_model: type,
) -> Any:  # noqa: ANN401
    """Build an async route handler for *method_name* on *template*.

    Injects ``__signature__`` so FastAPI generates a correct OpenAPI schema
    for the dynamically created function.

    :param template: Template ABC class
    :type template: type
    :param method_name: name of the method to dispatch
    :type method_name: str
    :param request_model: Pydantic model for the request body
    :type request_model: type
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
            session, template, index
        )
        job = await session.queue.submit(
            lambda: getattr(device, method_name)(**body.model_dump()),
            mode=mode,
        )
        if mode == "async":
            return _async_response(job)
        return {"result": job.result}

    handler.__name__ = f"{template.__name__.lower()}_{method_name}"
    handler.__qualname__ = handler.__name__
    handler.__doc__ = (
        f"{method_name.replace('_', ' ').capitalize()} on"
        f" {template.__name__} device at *index*."
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


def _validate_sig(
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
        p.kind
        in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
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


def _process_member(
    template: type,
    name: str,
    obj: object,
) -> SkippedMethod | Any | None:  # noqa: ANN401
    """Process a single class member to determine route generation outcome.

    :param template: Template ABC class being introspected
    :type template: type
    :param name: attribute name from ``inspect.getmembers``
    :type name: str
    :param obj: attribute value (result of ``getattr(template, name)``)
    :type obj: object
    :return: a handler callable to register, a SkippedMethod, or None to
        skip silently
    :rtype: SkippedMethod | Any | None
    """
    raw = inspect.getattr_static(template, name, None)

    if isinstance(raw, (property, cached_property)):
        return SkippedMethod(template.__name__, name, "property")
    if not callable(obj) or isinstance(raw, (classmethod, staticmethod)):
        return None

    try:
        sig = inspect.signature(obj, eval_str=True)  # type: ignore[call-arg]
    except (ValueError, TypeError):
        return None
    except NameError:
        return SkippedMethod(
            template.__name__, name, "unevaluable annotation"
        )

    skipped = _validate_sig(template.__name__, name, sig)
    if skipped is not None:
        return skipped

    return _make_handler(template, name, _make_request_model(name, sig))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_template_routers(
    templates: list[type],
) -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Generate FastAPI routers for each template ABC.

    Reflects over public instance methods on each template, applies skip
    rules, and builds a route handler for each accepted method.  Skipped
    methods are collected, logged at WARNING, and returned alongside the
    routers.

    :param templates: template ABC classes to introspect
    :type templates: list[type]
    :return: generated routers and list of skipped methods with reasons
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
    routers: list[APIRouter] = []
    all_skipped: list[SkippedMethod] = []

    for template in templates:
        router = APIRouter(
            prefix=f"/templates/{template.__name__.lower()}",
            tags=[f"templates:{template.__name__.lower()}"],
        )
        for name, obj in inspect.getmembers(template):
            if name.startswith("__"):
                continue
            if name.startswith("_"):
                skipped = SkippedMethod(template.__name__, name, "private")
                all_skipped.append(skipped)
                _log.warning(
                    "template route skipped: %s.%s — private",
                    template.__name__,
                    name,
                )
                continue

            result = _process_member(template, name, obj)
            if result is None:
                continue
            if isinstance(result, SkippedMethod):
                all_skipped.append(result)
                _log.warning(
                    "template route skipped: %s.%s — %s",
                    template.__name__,
                    result.method,
                    result.reason,
                )
                continue

            handler = result
            router.post(f"/{name}", status_code=200, response_model=None)(handler)
            router.post(
                f"/{{index}}/{name}", status_code=200, response_model=None
            )(handler)

        routers.append(router)

    return routers, all_skipped
