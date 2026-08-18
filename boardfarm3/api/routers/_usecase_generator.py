"""Runtime use-case router generator for the boardfarm API.

Introspects public functions in the ``boardfarm3.use_cases`` modules and
builds FastAPI routes.  Device-typed parameters are resolved from the running
device registry by name; primitive parameters come from the request body.
"""

from __future__ import annotations

import inspect  # noqa: F401  # pylint: disable=unused-import
import logging
from typing import Any, Literal, Union, get_args, get_origin

from boardfarm3.api.routers._generator import (  # noqa: F401  # pylint: disable=unused-import
    _NONE_TYPE,
    _UNION_TYPE,
    SkippedMethod,
    _is_serialisable,
)

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
