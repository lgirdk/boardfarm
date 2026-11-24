"""Type substitution and coercion shared by the router generators and adapters.

Kept apart from ``_generator`` so ``adapter`` can import it at module scope:
``_generator`` imports ``adapter``, so importing ``_generator`` back would cycle.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin

# Guard for the Python 3.10+ union syntax type (X | Y).
_UNION_TYPE: type | None = getattr(types, "UnionType", None)  # pylint: disable=invalid-name

# NoneType singleton — avoids calling type() at check time (pylint C0123).
_NONE_TYPE: type = type(None)  # pylint: disable=invalid-name


def _annotation_to_field_type(  # pylint: disable=too-many-return-statements  # noqa: PLR0911
    annotation: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Return an API-friendly substitute for *annotation*.

    Replaces ``Enum`` subclasses with ``Literal[member_names]`` and
    ``tuple`` origins with ``list`` so FastAPI/Pydantic can generate a
    JSON schema.  All other annotations are returned unchanged.

    :param annotation: original type annotation
    :type annotation: Any
    :return: substituted annotation suitable for a Pydantic model field
    :rtype: Any
    """
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return Literal[tuple(m.name for m in annotation)]
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is tuple:
        if not args:
            return list
        if args[-1] is Ellipsis:
            return list[_annotation_to_field_type(args[0])]  # type: ignore[misc]
        substituted = tuple(_annotation_to_field_type(a) for a in args)
        inner = Union[substituted] if len(substituted) > 1 else substituted[0]
        return list[inner]  # type: ignore[misc, valid-type]
    if origin is list and args:
        return list[_annotation_to_field_type(args[0])]  # type: ignore[misc]
    if origin is dict and len(args) == 2:  # noqa: PLR2004
        return dict[  # type: ignore[misc]
            _annotation_to_field_type(args[0]),
            _annotation_to_field_type(args[1]),
        ]
    is_union = (
        _UNION_TYPE is not None and isinstance(annotation, _UNION_TYPE)
    ) or origin is Union
    if is_union and args:
        return Union[tuple(_annotation_to_field_type(a) for a in args)]
    return annotation


@dataclass
class _CoercionPlan:
    """Per-call coercion map from API-friendly types back to Python types.

    :param coercions: mapping from parameter name to its original annotation
    :type coercions: dict[str, Any]
    """

    coercions: dict[str, Any]


def _coerce(  # pylint: disable=too-many-return-statements  # noqa: PLR0911
    value: Any,  # noqa: ANN401
    ann: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Recursively coerce *value* from its JSON form to the Python type *ann*.

    Handles ``Enum`` (name string -> member), ``tuple`` (list -> tuple),
    ``list[T]`` (element-wise), and ``Union``/optional (tries each non-None
    member in order).  All other annotations return *value* unchanged.

    :param value: the JSON-decoded value to coerce
    :type value: Any
    :param ann: the original Python type annotation
    :type ann: Any
    :return: coerced value matching *ann*
    :rtype: Any
    """
    if value is None:
        return None
    if isinstance(ann, type) and issubclass(ann, Enum):
        return ann[value]
    origin = get_origin(ann)
    args = get_args(ann)
    is_union = (
        _UNION_TYPE is not None and isinstance(ann, _UNION_TYPE)
    ) or origin is Union
    if is_union:
        non_none = [a for a in args if a is not _NONE_TYPE]
        for candidate in non_none:
            try:
                return _coerce(value, candidate)
            except (KeyError, TypeError, ValueError):  # noqa: PERF203
                pass
        return value
    if origin is tuple:
        if args and args[-1] is Ellipsis:
            return tuple(_coerce(v, args[0]) for v in value)
        return tuple(_coerce(v, a) for v, a in zip(value, args))
    if origin is list and args:
        return [_coerce(v, args[0]) for v in value]
    return value
