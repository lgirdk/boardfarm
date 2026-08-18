"""Runtime use-case router generator for the boardfarm API.

Introspects public functions in the ``boardfarm3.use_cases`` modules and
builds FastAPI routes.  Device-typed parameters are resolved from the running
device registry by name; primitive parameters come from the request body.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Literal, Union, get_args, get_origin

from fastapi import APIRouter, HTTPException, Request
from pydantic import create_model

from boardfarm3.api.routers import _async_response
from boardfarm3.api.routers._generator import (
    _NONE_TYPE,
    _UNION_TYPE,
    SkippedMethod,
    _is_serialisable,
)
from boardfarm3.exceptions import DeviceNotFound

if TYPE_CHECKING:
    from types import ModuleType

    from fastapi.responses import JSONResponse

_log = logging.getLogger(__name__)

_TEMPLATE_ROOT = "boardfarm3.templates"


def _is_template(annotation: Any) -> bool:  # noqa: ANN401
    """Return True when *annotation* is a template ABC class.

    :param annotation: a type annotation
    :type annotation: Any
    :return: True when the annotation is a class under boardfarm3.templates
    :rtype: bool
    """
    return isinstance(annotation, type) and annotation.__module__.startswith(
        _TEMPLATE_ROOT
    )


def _union_args(annotation: Any) -> tuple[Any, ...]:  # noqa: ANN401
    """Return the non-None args of a union annotation, or ().

    :param annotation: a type annotation
    :type annotation: Any
    :return: union member types excluding NoneType, or empty tuple
    :rtype: tuple[Any, ...]
    """
    origin = get_origin(annotation)
    is_union = (
        _UNION_TYPE is not None and isinstance(annotation, _UNION_TYPE)
    ) or origin is Union
    if not is_union:
        return ()
    return tuple(a for a in get_args(annotation) if a is not _NONE_TYPE)


def _template_types(annotation: Any) -> tuple[type, ...]:  # noqa: ANN401
    """Return the concrete template classes an annotation resolves to.

    :param annotation: a device-typed annotation (template or union thereof)
    :type annotation: Any
    :return: tuple of template classes for isinstance checks
    :rtype: tuple[type, ...]
    """
    if _is_template(annotation):
        return (annotation,)
    return tuple(a for a in _union_args(annotation) if _is_template(a))


def _classify_param(  # pylint: disable=too-many-return-statements
    annotation: Any,  # noqa: ANN401
) -> str:
    """Classify a parameter annotation for route generation.

    :param annotation: the parameter's type annotation
    :type annotation: Any
    :return: one of ``"device"``, ``"primitive"``, ``"unroutable"``
    :rtype: str
    """
    if _is_template(annotation):
        return "device"
    args = _union_args(annotation)
    if args and all(_is_template(a) for a in args):
        return "device"
    if get_origin(annotation) is Literal:
        return "primitive"
    if _is_serialisable(annotation):
        return "primitive"
    return "unroutable"


@dataclass
class _ParamPlan:
    """Resolution plan for one function parameter.

    :param name: parameter name
    :type name: str
    :param is_device: whether the parameter is resolved from the registry
    :type is_device: bool
    :param templates: template classes accepted (device params only)
    :type templates: tuple[type, ...]
    """

    name: str
    is_device: bool
    templates: tuple[type, ...]


def _build_request_model(fn_name: str, sig: inspect.Signature) -> type:
    """Build a flat Pydantic model; device params become str name fields.

    :param fn_name: function name, used for the model class name
    :type fn_name: str
    :param sig: the function signature
    :type sig: inspect.Signature
    :return: dynamically created Pydantic model
    :rtype: type
    """
    fields: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        default = param.default if param.default is not inspect.Parameter.empty else ...
        if _classify_param(param.annotation) == "device":
            fields[name] = (str, ... if default is ... else default)
        else:
            fields[name] = (param.annotation, default)
    model_name = "".join(p.capitalize() for p in fn_name.split("_")) + "Request"
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def _make_usecase_handler(
    fn: Any,  # noqa: ANN401
    request_model: type,
    plans: list[_ParamPlan],
) -> Any:  # noqa: ANN401
    """Build an async handler that resolves device params then calls *fn*.

    :param fn: the use-case function to invoke
    :type fn: Any
    :param request_model: Pydantic model for the request body
    :type request_model: type
    :param plans: per-parameter resolution plans
    :type plans: list[_ParamPlan]
    :return: async FastAPI route handler
    :rtype: Any
    """

    async def handler(
        request: Request,
        body: Any,  # noqa: ANN401
        mode: str = "sync",
    ) -> dict[str, Any] | JSONResponse:
        session = request.app.state.session
        dm = session.runtime.device_manager
        if dm is None:
            raise HTTPException(
                status_code=int(HTTPStatus.CONFLICT),
                detail="session is not booted — device_manager unavailable",
            )
        data = body.model_dump()
        kwargs: dict[str, Any] = {}
        for plan in plans:
            if not plan.is_device:
                kwargs[plan.name] = data[plan.name]
                continue
            name = data[plan.name]
            try:
                device = dm.get_device_by_name(name)
            except DeviceNotFound as exc:
                raise HTTPException(
                    status_code=int(HTTPStatus.NOT_FOUND),
                    detail=f"no device named {name!r}",
                ) from exc
            if not isinstance(device, plan.templates):
                raise HTTPException(
                    status_code=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                    detail=(
                        f"device {name!r} is not one of "
                        f"{[t.__name__ for t in plan.templates]}"
                    ),
                )
            kwargs[plan.name] = device
        job = await session.queue.submit(lambda: fn(**kwargs), mode=mode)
        if mode == "async":
            return _async_response(job)
        return {"result": job.result}

    handler.__name__ = f"usecase_{fn.__name__}"
    handler.__qualname__ = handler.__name__
    handler.__doc__ = (fn.__doc__ or fn.__name__).strip().splitlines()[0]
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
                "mode",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default="sync",
                annotation=Literal["sync", "async"],
            ),
        ]
    )
    return handler


def _plan_params(  # pylint: disable=too-many-return-statements
    module_name: str, fn_name: str, sig: inspect.Signature
) -> SkippedMethod | list[_ParamPlan]:
    """Validate and classify every parameter of a signature.

    :param module_name: short module name for SkippedMethod records
    :type module_name: str
    :param fn_name: function name
    :type fn_name: str
    :param sig: the function signature
    :type sig: inspect.Signature
    :return: SkippedMethod when a parameter is unroutable, else param plans
    :rtype: SkippedMethod | list[_ParamPlan]
    """
    plans: list[_ParamPlan] = []
    for name, param in sig.parameters.items():
        if param.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            return SkippedMethod(module_name, fn_name, "has *args or **kwargs")
        if param.annotation is inspect.Parameter.empty:
            return SkippedMethod(module_name, fn_name, f"missing annotation on: {name}")
        kind = _classify_param(param.annotation)
        if kind == "unroutable":
            return SkippedMethod(module_name, fn_name, f"unroutable parameter: {name}")
        plans.append(
            _ParamPlan(name, kind == "device", _template_types(param.annotation))
        )
    return plans


def _check_return_type(
    module_name: str,
    fn_name: str,
    ret: Any,  # noqa: ANN401
) -> SkippedMethod | None:
    """Validate that a function's return annotation is routable.

    :param module_name: short module name for SkippedMethod records
    :type module_name: str
    :param fn_name: function name
    :type fn_name: str
    :param ret: the function's return annotation
    :type ret: Any
    :return: SkippedMethod when the return type is unroutable, else None
    :rtype: SkippedMethod | None
    """
    if ret is inspect.Parameter.empty:
        return SkippedMethod(module_name, fn_name, "missing return annotation")
    # A bare ``Any`` return gives no schema guarantee for a use-case route,
    # so treat it as non-serialisable here even though the shared
    # ``_is_serialisable`` (reused for param classification) accepts it.
    if ret is Any or not _is_serialisable(ret):
        return SkippedMethod(
            module_name, fn_name, f"non-serialisable return type: {ret!r}"
        )
    return None


def _signature_or_skip(
    module_name: str,
    fn_name: str,
    fn: Any,  # noqa: ANN401
) -> SkippedMethod | inspect.Signature:
    """Resolve a function's signature, recording why it failed if it can't.

    :param module_name: short module name for SkippedMethod records
    :type module_name: str
    :param fn_name: function name
    :type fn_name: str
    :param fn: the function object
    :type fn: Any
    :return: SkippedMethod when unresolvable, else the resolved signature
    :rtype: SkippedMethod | inspect.Signature
    """
    try:
        return inspect.signature(fn, eval_str=True)
    except (ValueError, TypeError):
        return SkippedMethod(module_name, fn_name, "unintrospectable signature")
    except NameError:
        return SkippedMethod(module_name, fn_name, "unevaluable annotation")


def _plan_function(  # pylint: disable=too-many-return-statements
    module_name: str,
    fn_name: str,
    fn: Any,  # noqa: ANN401
) -> SkippedMethod | tuple[type, list[_ParamPlan]]:
    """Validate a function and return its request model + param plans.

    :param module_name: short module name for SkippedMethod records
    :type module_name: str
    :param fn_name: function name
    :type fn_name: str
    :param fn: the function object
    :type fn: Any
    :return: SkippedMethod when unroutable, else (request_model, plans)
    :rtype: SkippedMethod | tuple[type, list[_ParamPlan]]
    """
    sig = _signature_or_skip(module_name, fn_name, fn)
    if isinstance(sig, SkippedMethod):
        return sig

    plans = _plan_params(module_name, fn_name, sig)
    if isinstance(plans, SkippedMethod):
        return plans

    skipped = _check_return_type(module_name, fn_name, sig.return_annotation)
    if skipped is not None:
        return skipped

    return _build_request_model(fn_name, sig), plans


def generate_usecase_routers(
    modules: list[ModuleType],
) -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Generate FastAPI routers for the public functions of each module.

    :param modules: use-case modules to introspect
    :type modules: list[ModuleType]
    :return: generated routers and skipped functions with reasons
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
    routers: list[APIRouter] = []
    all_skipped: list[SkippedMethod] = []

    for module in modules:
        short = module.__name__.rsplit(".", 1)[-1]
        router = APIRouter(
            prefix=f"/use_cases/{short}",
            tags=[f"use_cases:{short}"],
        )
        for fn_name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn_name.startswith("_"):
                continue
            if getattr(fn, "__module__", "") != module.__name__:
                continue  # skip imported symbols
            result = _plan_function(short, fn_name, fn)
            if isinstance(result, SkippedMethod):
                all_skipped.append(result)
                _log.warning(
                    "use-case route skipped: %s.%s — %s",
                    short,
                    result.method,
                    result.reason,
                )
                continue
            request_model, plans = result
            handler = _make_usecase_handler(fn, request_model, plans)
            router.post(f"/{fn_name}", status_code=200, response_model=None)(handler)
        routers.append(router)

    return routers, all_skipped
