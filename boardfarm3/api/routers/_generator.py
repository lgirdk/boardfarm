"""Runtime template router generator for boardfarm API.

Introspects Template ABCs at agent startup and builds FastAPI routes
for all public methods with JSON-serialisable signatures.
"""

from __future__ import annotations

import inspect
import logging
import re
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import (
    Any,
    Literal,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from fastapi import APIRouter, Request
from pydantic import Field, create_model

from boardfarm3.api.holds import ALL
from boardfarm3.api.routers import _resolve
from boardfarm3.api.routers._types import (
    _NONE_TYPE,
    _UNION_TYPE,
    _annotation_to_field_type,
    _CoercionPlan,
)
from boardfarm3.api.routers.adapter import (
    DefaultAdapter,
    Outcome,
    ResponseAdapter,
    Unsupported,
)

_log = logging.getLogger(__name__)

# Primitive types that are directly JSON-serialisable.
_PRIMITIVE_TYPES: frozenset[type] = frozenset({str, int, float, bool, dict, list})

# ---------------------------------------------------------------------------
# Serialisability check
# ---------------------------------------------------------------------------


def _is_serialisable(  # pylint: disable=too-many-return-statements  # noqa: PLR0911
    annotation: Any,  # noqa: ANN401
) -> bool:
    """Return True if *annotation* is JSON-serialisable.

    Accepts ``None``/``NoneType``, ``typing.Any``, primitives, ``tuple``,
    ``Enum`` subclasses, ``TypedDict`` types, and Unions/generics thereof.

    :param annotation: a type annotation to check
    :type annotation: Any
    :return: True when the type can be expressed as JSON
    :rtype: bool
    """
    if (
        annotation is None
        or annotation is _NONE_TYPE
        or annotation is Any
        or annotation in _PRIMITIVE_TYPES
    ):
        return True
    # Enum subclasses serialise as their member names (Literal).
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return True
    # TypedDict: all annotated values must be serialisable.
    if is_typeddict(annotation):
        try:
            hints = get_type_hints(annotation)
        except (NameError, TypeError, AttributeError):
            hints = annotation.__annotations__
        return all(_is_serialisable(v) for v in hints.values())
    origin = get_origin(annotation)
    # tuple[X, Y, Z] and tuple[str, ...] serialise as JSON arrays.
    if origin is tuple:
        args = get_args(annotation)
        if not args:
            return True
        if args[-1] is Ellipsis:
            return _is_serialisable(args[0])
        return all(_is_serialisable(a) for a in args)
    # Union types (both X | Y and Union[X, Y]) and generic dict/list.
    is_union = (
        _UNION_TYPE is not None and isinstance(annotation, _UNION_TYPE)
    ) or origin is Union
    if is_union or origin in (dict, list):
        return all(_is_serialisable(a) for a in get_args(annotation))
    return False


_SPHINX_PARAM_RE: re.Pattern[str] = re.compile(
    r":param\s+(\w+):\s*(.+?)(?=\n\s*:|$)", re.DOTALL
)


def _parse_sphinx_params(docstring: str | None) -> dict[str, str]:
    """Extract ``:param name: description`` entries from a Sphinx docstring.

    :param docstring: raw docstring text, or None
    :type docstring: str | None
    :return: mapping from parameter name to collapsed description text
    :rtype: dict[str, str]
    """
    if not docstring:
        return {}
    return {
        m.group(1): " ".join(m.group(2).split())
        for m in _SPHINX_PARAM_RE.finditer(docstring)
    }


# ---------------------------------------------------------------------------
# Response documentation (docs-only; runtime bodies are built by the adapter)
# ---------------------------------------------------------------------------

_ASYNC_TICKET_MODEL = create_model(  # documents the 202 mode=async ticket
    "AsyncJobTicket",
    job_id=(str, ...),
    state=(str, ...),
)


def _response_docs(
    method_name: str,
    return_annotation: Any,  # noqa: ANN401
    adapter: ResponseAdapter,
) -> dict[int | str, dict[str, Any]] | None:
    """Build docs-only ``responses`` metadata for a generated route.

    Only the exact native :class:`DefaultAdapter` gets documentation: a
    custom adapter defines its own response contract, and these models
    would misdescribe it. Attached via the route's ``responses`` mapping
    with ``response_model=None``, so FastAPI renders the schemas without
    ever validating or serialising through them.

    :param method_name: dispatched method name, used for the model name
    :type method_name: str
    :param return_annotation: the method's return annotation
    :type return_annotation: Any
    :param adapter: active response adapter
    :type adapter: ResponseAdapter
    :return: responses mapping for the route decorator, or None
    :rtype: dict[int | str, dict[str, Any]] | None
    """
    if type(adapter) is not DefaultAdapter:  # pylint: disable=unidiomatic-typecheck
        return None
    result_type = _annotation_to_field_type(return_annotation)
    if return_annotation is None or return_annotation is _NONE_TYPE:
        result_type = None
    doc_model = create_model(
        "".join(part.capitalize() for part in method_name.split("_")) + "Result",
        result=(result_type, ...),
    )
    docs: dict[int | str, dict[str, Any]] = {
        200: {"model": doc_model, "description": "Completed (mode=sync)."},
    }
    if adapter.supports_async:
        docs[202] = {
            "model": _ASYNC_TICKET_MODEL,
            "description": "Queued (mode=async); poll GET /jobs/{job_id}.",
        }
    return docs


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


def _adapter_field(
    active: ResponseAdapter,
    name: str,
    annotation: Any,  # noqa: ANN401
    default: Any,  # noqa: ANN401
    description: str,
) -> tuple[tuple[Any, Any], bool] | Unsupported:
    """Return one parameter's model field, and whether it needs coercion.

    :param active: the adapter choosing the field type
    :type active: ResponseAdapter
    :param name: parameter name
    :type name: str
    :param annotation: the parameter's Python type annotation
    :type annotation: Any
    :param default: the parameter's default, or ``...`` when required
    :type default: Any
    :param description: the parameter's description, empty for none
    :type description: str
    :return: ``((type, default), coerce)``, or Unsupported to skip the callable
    :rtype: tuple[tuple[Any, Any], bool] | Unsupported
    """
    spec = active.field_spec_for(name, annotation, default)
    if isinstance(spec, Unsupported):
        return spec
    field_type, field_default = spec
    if description:
        field_default = Field(default=field_default, description=description)
    return (field_type, field_default), field_type is not annotation


def _finish_request_model(
    model_name: str,
    fields: dict[str, Any],
    coercions: dict[str, Any],
    active: ResponseAdapter,
) -> tuple[type, _CoercionPlan] | Unsupported:
    """Add the adapter's extra fields to *fields* and create the request model.

    :param model_name: class name of the model
    :type model_name: str
    :param fields: the parameters' fields; the extra fields are added to it
    :type fields: dict[str, Any]
    :param coercions: parameter name to original annotation, for the plan
    :type coercions: dict[str, Any]
    :param active: the adapter contributing extra fields
    :type active: ResponseAdapter
    :return: (Pydantic model, coercion plan), or Unsupported when an extra
        field collides with a parameter
    :rtype: tuple[type, _CoercionPlan] | Unsupported
    """
    extra = active.extra_fields()
    collision = next((name for name in extra if name in fields), None)
    if collision is not None:
        return Unsupported(f"extra field collides with parameter {collision!r}")
    fields.update(extra)
    return (
        create_model(model_name, **fields),  # type: ignore[call-overload]
        _CoercionPlan(coercions=coercions),
    )


def _make_request_model(
    method_name: str,
    sig: inspect.Signature,
    docstring: str | None = None,
    *,
    adapter: ResponseAdapter | None = None,
) -> tuple[type, _CoercionPlan] | Unsupported:
    """Build a Pydantic model from the non-self parameters of *sig*.

    Enum annotations are substituted with ``Literal[member_names]`` and
    ``tuple`` annotations with ``list`` in the model fields.  A
    :class:`_CoercionPlan` records which parameters need coercion at
    call time.

    :param method_name: used to derive the model class name
    :type method_name: str
    :param sig: method signature (``self`` is excluded)
    :type sig: inspect.Signature
    :param docstring: raw method docstring for Sphinx param extraction
    :type docstring: str | None
    :param adapter: response adapter controlling field types and extra fields;
        None uses the native default
    :type adapter: ResponseAdapter | None
    :return: (Pydantic model, coercion plan), or Unsupported to skip the method
    :rtype: tuple[type, _CoercionPlan] | Unsupported
    """
    active = adapter or DefaultAdapter()
    fields: dict[str, Any] = {}
    coercions: dict[str, Any] = {}
    param_descriptions = _parse_sphinx_params(docstring)
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        annotation = param.annotation
        default = param.default if param.default is not inspect.Parameter.empty else ...
        field = _adapter_field(
            active, name, annotation, default, param_descriptions.get(name, "")
        )
        if isinstance(field, Unsupported):
            return field
        fields[name], coerce = field
        if coerce:
            coercions[name] = annotation
    model_name = (
        "".join(part.capitalize() for part in method_name.split("_")) + "Request"
    )
    return _finish_request_model(model_name, fields, coercions, active)


def _make_handler(  # noqa: PLR0913
    resolve_as: type,
    introspect: type,
    method_name: str,
    request_model: type,
    accessor: str | None,
    coercion_plan: _CoercionPlan,
    required: frozenset[str],
    adapter: ResponseAdapter,
) -> Any:  # noqa: ANN401
    """Build an async route handler for *method_name*.

    Injects ``__signature__`` so FastAPI generates a correct OpenAPI schema
    for the dynamically created function.  Parameters in *coercion_plan* are
    translated from their API-friendly form back to the real Python type before
    dispatching.

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
    :param coercion_plan: parameters requiring type coercion before the call
    :type coercion_plan: _CoercionPlan
    :param required: names of parameters that had no default
    :type required: frozenset[str]
    :param adapter: response adapter controlling coercion, checks and body
    :type adapter: ResponseAdapter
    :return: async FastAPI route handler
    :rtype: Any
    """
    extra_names = tuple(adapter.extra_fields())

    async def handler(
        request: Request,
        body: Any,  # noqa: ANN401
        index: int = 0,
        mode: str = "sync",
    ) -> Any:  # noqa: ANN401
        effective_mode = mode if adapter.supports_async else "sync"
        short_circuit = adapter.check_request(body, required)
        if short_circuit is not None:
            return short_circuit
        job = None
        try:
            session = request.app.state.session
            device: Any = _resolve(  # type: ignore[type-abstract]
                session, resolve_as, index
            )
            target = device if accessor is None else getattr(device, accessor)

            def _run() -> Any:  # noqa: ANN401
                data = body.model_dump()
                for p_name, orig_ann in coercion_plan.coercions.items():
                    if p_name in data:
                        data[p_name] = adapter.coerce(data[p_name], orig_ann)
                # Adapter-injected fields are transport concerns; the target
                # method never declared them and would raise TypeError.
                for extra in extra_names:
                    data.pop(extra, None)
                return getattr(target, method_name)(**data)

            job = await session.queue.submit(
                _run,
                mode=effective_mode,
                devices=frozenset({getattr(device, "device_name", ALL)}),
            )
            outcome = Outcome(
                job=job,
                value=job.result if effective_mode != "async" else None,
                error=None,
                mode=effective_mode,
            )
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            # Safe because DefaultAdapter.respond re-raises, preserving the
            # native path. Only an adapter that opts in absorbs the error.
            outcome = Outcome(job=job, value=None, error=exc, mode=effective_mode)
        return adapter.respond(outcome)

    handler.__name__ = f"{introspect.__name__.lower()}_{method_name}"
    handler.__qualname__ = handler.__name__
    handler.__doc__ = (
        f"{method_name.replace('_', ' ').capitalize()} on"
        f" {introspect.__name__} device at *index*."
    )
    params = [
        inspect.Parameter(
            "request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request
        ),
        inspect.Parameter(
            "body", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=request_model
        ),
        inspect.Parameter(
            "index",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=0,
            annotation=int,
        ),
    ]
    if adapter.supports_async:
        params.append(
            inspect.Parameter(
                "mode",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default="sync",
                annotation=Literal["sync", "async"],
            )
        )
    handler.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
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

    # A parameter annotated with a non-JSON type (typically another Template
    # ABC, e.g. ``configure_aftr(self, wan: WAN)``) cannot become a Pydantic
    # body field.  Reject it here rather than letting ``create_model`` raise.
    unroutable = [
        f"{p_name}: {p.annotation!r}"
        for p_name, p in sig.parameters.items()
        if p_name != "self" and not _is_serialisable(p.annotation)
    ]
    if unroutable:
        return SkippedMethod(
            template_name,
            name,
            f"non-serialisable param type: {', '.join(unroutable)}",
        )

    ret = sig.return_annotation
    if ret is inspect.Parameter.empty:
        return SkippedMethod(template_name, name, "missing return annotation")
    if not _is_serialisable(ret):
        return SkippedMethod(
            template_name, name, f"non-serialisable return type: {ret!r}"
        )

    return None


def _process_member(  # pylint: disable=too-many-return-statements  # noqa: PLR0911
    introspect: type,
    name: str,
    obj: object,
    adapter: ResponseAdapter,
) -> SkippedMethod | tuple[type, _CoercionPlan, frozenset[str], Any] | None:
    """Process a single class member to determine route generation outcome.

    :param introspect: Template ABC class being introspected
    :type introspect: type
    :param name: attribute name from ``inspect.getmembers``
    :type name: str
    :param obj: attribute value (result of ``getattr(introspect, name)``)
    :type obj: object
    :param adapter: response adapter controlling field types and extra fields
    :type adapter: ResponseAdapter
    :return: a (Pydantic request model, coercion plan, required parameter
        names) tuple to register a route for, a SkippedMethod, or None to
        skip silently
    :rtype: SkippedMethod | tuple[type, _CoercionPlan, frozenset[str], Any] | None
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

    result = _make_request_model(
        name,
        sig,
        obj.__doc__ if callable(obj) else None,
        adapter=adapter,
    )
    if isinstance(result, Unsupported):
        return SkippedMethod(introspect.__name__, name, result.reason)
    request_model, coercion_plan = result
    required = frozenset(
        p_name
        for p_name, p in sig.parameters.items()
        if p_name != "self" and p.default is inspect.Parameter.empty
    )
    return request_model, coercion_plan, required, sig.return_annotation


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
    :param adapter: response adapter controlling route generation and dispatch
    :type adapter: ResponseAdapter
    """

    mount: str
    router: APIRouter
    seen: set[str]
    all_skipped: list[SkippedMethod]
    adapter: ResponseAdapter


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

    result = _process_member(spec.introspect, name, obj, build.adapter)
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

    request_model, coercion_plan, required, return_annotation = result
    handler = _make_handler(
        spec.resolve_as,
        spec.introspect,
        name,
        request_model,
        spec.accessor,
        coercion_plan,
        required,
        build.adapter,
    )
    build.seen.add(name)
    router = build.router
    docs = _response_docs(name, return_annotation, build.adapter)
    router.post(f"/{name}", status_code=200, response_model=None, responses=docs)(
        handler
    )
    router.post(
        f"/{{index}}/{name}", status_code=200, response_model=None, responses=docs
    )(handler)


def generate_template_routers(
    templates: list[type | TemplateMount],
    *,
    adapter: ResponseAdapter | None = None,
) -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Generate FastAPI routers for each template mount.

    Bare template types are treated as a single-source mount. Multiple
    ``TemplateMount`` specs sharing a ``mount`` flatten into one router; a
    method name contributed by more than one spec is kept from the first
    spec only and the rest are skipped.

    :param templates: template classes or TemplateMount specs to introspect
    :type templates: list[type | TemplateMount]
    :param adapter: response adapter controlling route generation and
        dispatch; None uses the native default
    :type adapter: ResponseAdapter | None
    :return: generated routers and list of skipped methods with reasons
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
    active = adapter or DefaultAdapter()
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
        build = _MountBuild(mount, router, set(), all_skipped, active)
        for spec in grouped[mount]:
            for name, obj in inspect.getmembers(spec.introspect):
                _register_member(build, spec, name, obj)

        routers.append(router)

    return routers, all_skipped
