# Generator Type Expansion & API Description Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the boardfarm API route generators to handle `tuple`, `Enum`, and `TypedDict` annotations, coerce them back to real Python types at call time, and inject Sphinx `:param:` descriptions as Pydantic `Field(description=...)` for Swagger UI.

**Architecture:** Pure helper functions (`_is_serialisable` expansion, `_annotation_to_field_type`, `_CoercionPlan`, `_coerce`, `_parse_sphinx_params`) are added to `_generator.py` first (Task 1, no behaviour change). Tasks 2–3 wire them into the two generator files, updating return types and handler closures. Task 4 smoke-verifies coverage with a real use-case.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, `inspect`, `re`, `enum.Enum`, `typing.TypedDict`, pytest.

## Global Constraints

- Python 3.11–3.13 compatibility required; no 3.12-only syntax.
- All public APIs must have Sphinx-style docstrings (`:param:`, `:type:`, `:return:`, `:rtype:`).
- `ruff`, `flake8` (darglint2), `mypy --disallow-untyped-defs`, `pylint` must all pass.
- `set` and `frozenset` are intentionally NOT added to `_is_serialisable` — no JSON equivalent.
- Do not change `boardfarm3/api/app.py`.
- Run tests with: `pytest unittests/api/ -v`

---

### Task 1: Pure helper functions in `_generator.py`

**Files:**
- Modify: `boardfarm3/api/routers/_generator.py`
- Test: `unittests/api/test_generator.py`

**Interfaces:**
- Produces for Tasks 2 & 3:
  - `_annotation_to_field_type(annotation: Any) -> Any`
  - `_CoercionPlan` dataclass with field `coercions: dict[str, Any]`
  - `_coerce(value: Any, ann: Any) -> Any`
  - `_parse_sphinx_params(docstring: str | None) -> dict[str, str]`
  - `_is_serialisable` extended to return `True` for `tuple`, `Enum`, `TypedDict`

- [ ] **Step 1: Write failing tests for `_is_serialisable` new cases**

Add to `unittests/api/test_generator.py` after the existing imports:

```python
from enum import Enum
from typing import TypedDict

from boardfarm3.api.routers._generator import (
    _annotation_to_field_type,
    _CoercionPlan,
    _coerce,
    _is_serialisable,
    _parse_sphinx_params,
)


# ---------------------------------------------------------------------------
# _is_serialisable — new cases
# ---------------------------------------------------------------------------


class _Color(Enum):
    RED = 1
    BLUE = 2


class _Coord(TypedDict):
    x: float
    y: float


def test_is_serialisable_tuple_of_primitives() -> None:
    assert _is_serialisable(tuple[str, int]) is True


def test_is_serialisable_tuple_uniform() -> None:
    assert _is_serialisable(tuple[str, ...]) is True


def test_is_serialisable_empty_tuple() -> None:
    assert _is_serialisable(tuple[()]) is True  # type: ignore[misc]


def test_is_serialisable_enum() -> None:
    assert _is_serialisable(_Color) is True


def test_is_serialisable_typeddict() -> None:
    assert _is_serialisable(_Coord) is True


def test_is_serialisable_nested_tuple_in_list() -> None:
    assert _is_serialisable(list[tuple[str, int]]) is True


def test_is_serialisable_set_remains_false() -> None:
    assert _is_serialisable(set[str]) is False  # type: ignore[type-arg]


def test_is_serialisable_typeddict_with_bad_value_false() -> None:
    class _Bad(TypedDict):
        obj: object

    assert _is_serialisable(_Bad) is False


# ---------------------------------------------------------------------------
# _annotation_to_field_type
# ---------------------------------------------------------------------------


def test_annotation_to_field_type_primitive_unchanged() -> None:
    assert _annotation_to_field_type(str) is str
    assert _annotation_to_field_type(int) is int
    assert _annotation_to_field_type(bool) is bool


def test_annotation_to_field_type_enum_becomes_literal() -> None:
    from typing import Literal, get_args, get_origin

    result = _annotation_to_field_type(_Color)
    assert get_origin(result) is Literal
    assert set(get_args(result)) == {"RED", "BLUE"}


def test_annotation_to_field_type_tuple_fixed_becomes_list_union() -> None:
    from typing import Union, get_args, get_origin

    result = _annotation_to_field_type(tuple[str, int])
    assert get_origin(result) is list
    inner = get_args(result)[0]
    assert set(get_args(inner)) == {str, int}


def test_annotation_to_field_type_tuple_uniform_becomes_list() -> None:
    result = _annotation_to_field_type(tuple[str, ...])
    from typing import get_args, get_origin

    assert get_origin(result) is list
    assert get_args(result) == (str,)


def test_annotation_to_field_type_list_with_enum_inner() -> None:
    from typing import Literal, get_args, get_origin

    result = _annotation_to_field_type(list[_Color])
    assert get_origin(result) is list
    inner = get_args(result)[0]
    assert get_origin(inner) is Literal


def test_annotation_to_field_type_typeddict_unchanged() -> None:
    assert _annotation_to_field_type(_Coord) is _Coord


# ---------------------------------------------------------------------------
# _CoercionPlan
# ---------------------------------------------------------------------------


def test_coercion_plan_empty() -> None:
    plan = _CoercionPlan(coercions={})
    assert plan.coercions == {}


def test_coercion_plan_stores_annotations() -> None:
    plan = _CoercionPlan(coercions={"records": list[tuple[str, _Color]]})
    assert plan.coercions["records"] == list[tuple[str, _Color]]


# ---------------------------------------------------------------------------
# _coerce
# ---------------------------------------------------------------------------


def test_coerce_primitive_unchanged() -> None:
    assert _coerce("hello", str) == "hello"
    assert _coerce(42, int) == 42


def test_coerce_enum_by_name() -> None:
    assert _coerce("RED", _Color) == _Color.RED


def test_coerce_fixed_tuple() -> None:
    result = _coerce(["RED", 42], tuple[_Color, int])
    assert result == (_Color.RED, 42)
    assert isinstance(result, tuple)


def test_coerce_uniform_tuple() -> None:
    result = _coerce(["a", "b"], tuple[str, ...])
    assert result == ("a", "b")
    assert isinstance(result, tuple)


def test_coerce_list_of_enum() -> None:
    result = _coerce(["RED", "BLUE"], list[_Color])
    assert result == [_Color.RED, _Color.BLUE]


def test_coerce_nested_list_of_tuple_with_enum() -> None:
    result = _coerce([["RED", "group1"], ["BLUE", "group2"]], list[tuple[_Color, str]])
    assert result == [(_Color.RED, "group1"), (_Color.BLUE, "group2")]


def test_coerce_optional_enum_none() -> None:
    result = _coerce(None, _Color | None)
    assert result is None


def test_coerce_optional_enum_value() -> None:
    result = _coerce("RED", _Color | None)
    assert result == _Color.RED


def test_coerce_typeddict_passthrough() -> None:
    data = {"x": 1.0, "y": 2.0}
    assert _coerce(data, _Coord) == data


# ---------------------------------------------------------------------------
# _parse_sphinx_params
# ---------------------------------------------------------------------------


def test_parse_sphinx_params_basic() -> None:
    doc = """Do something.\n\n:param name: the user name\n:param count: how many\n:return: result\n"""
    result = _parse_sphinx_params(doc)
    assert result == {"name": "the user name", "count": "how many"}


def test_parse_sphinx_params_multiline_collapsed() -> None:
    doc = ":param records: a list of\n    multicast records\n:return: nothing\n"
    result = _parse_sphinx_params(doc)
    assert result["records"] == "a list of multicast records"


def test_parse_sphinx_params_none() -> None:
    assert _parse_sphinx_params(None) == {}


def test_parse_sphinx_params_no_params() -> None:
    assert _parse_sphinx_params("Just a summary.") == {}


def test_parse_sphinx_params_ignores_type_lines() -> None:
    doc = ":param x: the x value\n:type x: int\n"
    result = _parse_sphinx_params(doc)
    assert "x" in result
    assert "type x" not in result  # :type x: should not be a key
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest unittests/api/test_generator.py -v -k "serialisable or annotation_to_field or CoercionPlan or coerce or sphinx"
```

Expected: collection errors (`ImportError: cannot import name '_annotation_to_field_type'`) or `FAILED`.

- [ ] **Step 3: Add imports to `_generator.py`**

At the top of `boardfarm3/api/routers/_generator.py`, add the following to the existing import block:

```python
import re
from enum import Enum
```

Add `Field` to the pydantic import:

```python
from pydantic import Field, create_model
```

- [ ] **Step 4: Expand `_is_serialisable` in `_generator.py`**

In `boardfarm3/api/routers/_generator.py`, replace the `_is_serialisable` function (lines 40–64) with:

```python
def _is_serialisable(annotation: Any) -> bool:  # noqa: ANN401
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
    if (
        isinstance(annotation, type)
        and hasattr(annotation, "__annotations__")
        and hasattr(annotation, "__total__")
    ):
        return all(
            _is_serialisable(v) for v in annotation.__annotations__.values()
        )
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
```

- [ ] **Step 5: Add `_annotation_to_field_type` to `_generator.py`**

Add after the `_is_serialisable` function, before the `SkippedMethod` dataclass:

```python
def _annotation_to_field_type(annotation: Any) -> Any:  # noqa: ANN401
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
            return list[_annotation_to_field_type(args[0])]  # type: ignore[valid-type]
        substituted = tuple(_annotation_to_field_type(a) for a in args)
        inner = Union[substituted] if len(substituted) > 1 else substituted[0]
        return list[inner]  # type: ignore[valid-type]
    if origin is list and args:
        return list[_annotation_to_field_type(args[0])]  # type: ignore[valid-type]
    if origin is dict and len(args) == 2:  # noqa: PLR2004
        return dict[  # type: ignore[valid-type]
            _annotation_to_field_type(args[0]),
            _annotation_to_field_type(args[1]),
        ]
    is_union = (
        _UNION_TYPE is not None and isinstance(annotation, _UNION_TYPE)
    ) or origin is Union
    if is_union and args:
        return Union[tuple(_annotation_to_field_type(a) for a in args)]
    return annotation
```

- [ ] **Step 6: Add `_CoercionPlan` dataclass to `_generator.py`**

Add after `_annotation_to_field_type`, still before `SkippedMethod`:

```python
@dataclass
class _CoercionPlan:
    """Per-call coercion map from API-friendly types back to Python types.

    :param coercions: mapping from parameter name to its original annotation
    :type coercions: dict[str, Any]
    """

    coercions: dict[str, Any]
```

- [ ] **Step 7: Add `_coerce` function to `_generator.py`**

Add after `_CoercionPlan`:

```python
def _coerce(value: Any, ann: Any) -> Any:  # noqa: ANN401
    """Recursively coerce *value* from its JSON form to the Python type *ann*.

    Handles ``Enum`` (name string → member), ``tuple`` (list → tuple),
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
            except (KeyError, TypeError, ValueError):
                pass
        return value
    if origin is tuple:
        if args and args[-1] is Ellipsis:
            return tuple(_coerce(v, args[0]) for v in value)
        return tuple(_coerce(v, a) for v, a in zip(value, args))
    if origin is list and args:
        return [_coerce(v, args[0]) for v in value]
    return value
```

- [ ] **Step 8: Add `_SPHINX_PARAM_RE` constant and `_parse_sphinx_params` to `_generator.py`**

Add after `_coerce`, still before `SkippedMethod`:

```python
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
```

- [ ] **Step 9: Run tests**

```bash
pytest unittests/api/test_generator.py -v -k "serialisable or annotation_to_field or CoercionPlan or coerce or sphinx"
```

Expected: all new tests pass.

- [ ] **Step 10: Run full lint check**

```bash
nox -s lint
```

Fix any ruff/mypy/flake8 complaints before committing.

- [ ] **Step 11: Commit**

```bash
git add boardfarm3/api/routers/_generator.py unittests/api/test_generator.py
git commit -m "feat(api): add tuple/Enum/TypedDict serialisability helpers and coercion plan"
```

---

### Task 2: Wire template generator (`_generator.py`)

**Files:**
- Modify: `boardfarm3/api/routers/_generator.py`
- Test: `unittests/api/test_generator.py`

**Interfaces:**
- Consumes from Task 1: `_annotation_to_field_type`, `_CoercionPlan`, `_coerce`, `_parse_sphinx_params`, `Field`
- `_make_request_model(method_name, sig, docstring)` now returns `tuple[type, _CoercionPlan]`
- `_process_member(introspect, name, obj)` now returns `SkippedMethod | tuple[type, _CoercionPlan] | None`
- `_make_handler(resolve_as, introspect, method_name, request_model, accessor, coercion_plan)` applies coercions in handler closure

- [ ] **Step 1: Write failing tests for wired template generator**

Add to `unittests/api/test_generator.py`:

```python
from enum import Enum as _Enum
from typing import Literal as _Literal, get_args, get_origin

from boardfarm3.api.routers._generator import _make_request_model


class _Direction(_Enum):
    UP = 1
    DOWN = 2


class _ABCWithEnum:
    def move(self, direction: _Direction, steps: int) -> None:
        """Move the device.

        :param direction: which way to move
        :param steps: number of steps
        """


def test_make_request_model_enum_field_is_literal() -> None:
    import inspect

    sig = inspect.signature(_ABCWithEnum.move)
    model, plan = _make_request_model("move", sig, _ABCWithEnum.move.__doc__)
    fields = model.model_fields
    assert "direction" in fields
    ann = fields["direction"].annotation
    assert get_origin(ann) is _Literal
    assert set(get_args(ann)) == {"UP", "DOWN"}


def test_make_request_model_coercion_plan_has_enum_entry() -> None:
    import inspect

    sig = inspect.signature(_ABCWithEnum.move)
    _, plan = _make_request_model("move", sig, _ABCWithEnum.move.__doc__)
    assert "direction" in plan.coercions
    assert plan.coercions["direction"] is _Direction


def test_make_request_model_primitive_no_coercion_entry() -> None:
    import inspect

    sig = inspect.signature(_ABCWithEnum.move)
    _, plan = _make_request_model("move", sig, _ABCWithEnum.move.__doc__)
    assert "steps" not in plan.coercions


def test_make_request_model_field_has_description() -> None:
    import inspect

    sig = inspect.signature(_ABCWithEnum.move)
    model, _ = _make_request_model("move", sig, _ABCWithEnum.move.__doc__)
    assert model.model_fields["direction"].description == "which way to move"
    assert model.model_fields["steps"].description == "number of steps"


def test_generate_template_routers_with_enum_param_produces_route() -> None:
    from abc import abstractmethod

    from boardfarm3.api.routers._generator import generate_template_routers

    class _ABCEnum:
        @abstractmethod
        def move(self, direction: _Direction, steps: int) -> None: ...

    routers, skipped = generate_template_routers([_ABCEnum])
    assert len(routers) == 1
    skipped_names = [s.method for s in skipped]
    assert "move" not in skipped_names
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest unittests/api/test_generator.py -v -k "make_request_model or enum_param"
```

Expected: `TypeError` or `ValueError` — `_make_request_model` still returns `type`, not `tuple`.

- [ ] **Step 3: Update `_make_request_model` in `_generator.py`**

Replace the existing `_make_request_model` function (lines 128–148) with:

```python
def _make_request_model(
    method_name: str,
    sig: inspect.Signature,
    docstring: str | None = None,
) -> tuple[type, _CoercionPlan]:
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
    :return: (Pydantic model, coercion plan)
    :rtype: tuple[type, _CoercionPlan]
    """
    fields: dict[str, Any] = {}
    coercions: dict[str, Any] = {}
    param_descriptions = _parse_sphinx_params(docstring)
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        annotation = param.annotation
        field_type = _annotation_to_field_type(annotation)
        if field_type is not annotation:
            coercions[name] = annotation
        default = (
            param.default if param.default is not inspect.Parameter.empty else ...
        )
        desc = param_descriptions.get(name, "")
        if desc:
            fields[name] = (field_type, Field(default=default, description=desc))
        else:
            fields[name] = (field_type, default)
    model_name = (
        "".join(part.capitalize() for part in method_name.split("_")) + "Request"
    )
    return (
        create_model(model_name, **fields),  # type: ignore[call-overload]
        _CoercionPlan(coercions=coercions),
    )
```

- [ ] **Step 4: Update `_make_handler` to accept and apply `coercion_plan`**

Replace `_make_handler` (lines 151–228) with:

```python
def _make_handler(
    resolve_as: type,
    introspect: type,
    method_name: str,
    request_model: type,
    accessor: str | None,
    coercion_plan: _CoercionPlan,
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

        def _run() -> Any:  # noqa: ANN401
            data = body.model_dump()
            for p_name, orig_ann in coercion_plan.coercions.items():
                if p_name in data:
                    data[p_name] = _coerce(data[p_name], orig_ann)
            return getattr(target, method_name)(**data)

        job = await session.queue.submit(_run, mode=mode)
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
```

- [ ] **Step 5: Update `_process_member` to unpack the model/plan tuple**

In `_process_member`, the final return statement currently is:

```python
    return _make_request_model(name, sig)
```

Replace it with:

```python
    return _make_request_model(name, sig, obj.__doc__ if callable(obj) else None)
```

And update the function's return annotation from `SkippedMethod | type | None` to `SkippedMethod | tuple[type, _CoercionPlan] | None`:

```python
def _process_member(  # pylint: disable=too-many-return-statements
    introspect: type,
    name: str,
    obj: object,
) -> SkippedMethod | tuple[type, _CoercionPlan] | None:
```

- [ ] **Step 6: Update `_register_member` to unpack and thread `coercion_plan`**

In `_register_member`, replace:

```python
    request_model = result
    handler = _make_handler(
        spec.resolve_as, spec.introspect, name, request_model, spec.accessor
    )
```

with:

```python
    request_model, coercion_plan = result
    handler = _make_handler(
        spec.resolve_as,
        spec.introspect,
        name,
        request_model,
        spec.accessor,
        coercion_plan,
    )
```

- [ ] **Step 7: Run tests**

```bash
pytest unittests/api/test_generator.py -v
```

Expected: all tests pass including the new ones.

- [ ] **Step 8: Run full lint**

```bash
nox -s lint
```

Fix any complaints.

- [ ] **Step 9: Commit**

```bash
git add boardfarm3/api/routers/_generator.py unittests/api/test_generator.py
git commit -m "feat(api): wire type coercion and field descriptions into template generator"
```

---

### Task 3: Wire use-case generator (`_usecase_generator.py`)

**Files:**
- Modify: `boardfarm3/api/routers/_usecase_generator.py`
- Test: `unittests/api/test_usecase_generator.py`

**Interfaces:**
- Consumes from Task 1: `_annotation_to_field_type`, `_CoercionPlan`, `_coerce`, `_parse_sphinx_params` (all imported from `_generator`)
- `_build_request_model(fn_name, sig, docstring)` now returns `tuple[type, _CoercionPlan]`
- `_plan_function(module_name, fn_name, fn)` now returns `SkippedMethod | tuple[type, list[_ParamPlan], _CoercionPlan]`
- `_make_usecase_handler(fn, request_model, plans, coercion_plan)` applies coercions to primitive params

- [ ] **Step 1: Write failing tests**

Add to `unittests/api/test_usecase_generator.py`:

```python
from enum import Enum

from boardfarm3.api.routers._usecase_generator import (
    _build_request_model,
    _classify_param,
)


class _Proto(Enum):
    TCP = 1
    UDP = 2


def _fake_sig_with_enum() -> "inspect.Signature":
    import inspect

    def fn(proto: _Proto, host: str) -> str:
        """Send probe.

        :param proto: transport protocol to use
        :param host: target hostname
        """

    return inspect.signature(fn)


def test_classify_param_enum_is_primitive() -> None:
    assert _classify_param(_Proto) == "primitive"


def test_build_request_model_enum_field_is_literal() -> None:
    import inspect
    from typing import Literal, get_args, get_origin

    def fn(proto: _Proto, host: str) -> str:
        """Send probe.

        :param proto: transport protocol to use
        :param host: target hostname
        """

    sig = inspect.signature(fn)
    model, plan = _build_request_model("fn", sig, fn.__doc__)
    ann = model.model_fields["proto"].annotation
    assert get_origin(ann) is Literal
    assert set(get_args(ann)) == {"TCP", "UDP"}
    assert plan.coercions.get("proto") is _Proto
    assert "host" not in plan.coercions


def test_build_request_model_field_has_description() -> None:
    import inspect

    def fn(proto: _Proto, host: str) -> str:
        """Send probe.

        :param proto: transport protocol to use
        :param host: target hostname
        """

    sig = inspect.signature(fn)
    model, _ = _build_request_model("fn", sig, fn.__doc__)
    assert model.model_fields["proto"].description == "transport protocol to use"
    assert model.model_fields["host"].description == "target hostname"


def test_generate_usecase_routers_enum_param_not_skipped() -> None:
    import types as _types

    from boardfarm3.api.routers._usecase_generator import generate_usecase_routers

    mod = _types.ModuleType("fake_uc_enum")
    mod.__name__ = "fake_uc_enum"

    def send_probe(proto: _Proto, host: str) -> str:
        """Send probe."""
        return f"{proto.name}:{host}"

    send_probe.__module__ = "fake_uc_enum"
    mod.send_probe = send_probe  # type: ignore[attr-defined]

    _, skipped = generate_usecase_routers([mod])
    assert not any(s.method == "send_probe" for s in skipped)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest unittests/api/test_usecase_generator.py -v -k "enum or description"
```

Expected: `TypeError` — `_build_request_model` still returns `type`.

- [ ] **Step 3: Update imports in `_usecase_generator.py`**

In `boardfarm3/api/routers/_usecase_generator.py`, replace the existing import from `_generator`:

```python
from boardfarm3.api.routers._generator import (
    _NONE_TYPE,
    _UNION_TYPE,
    SkippedMethod,
    _is_serialisable,
)
```

with:

```python
from boardfarm3.api.routers._generator import (
    _NONE_TYPE,
    _UNION_TYPE,
    _CoercionPlan,
    _annotation_to_field_type,
    _coerce,
    _parse_sphinx_params,
    SkippedMethod,
    _is_serialisable,
)
```

Also add `Field` to the pydantic import line:

```python
from pydantic import Field, create_model
```

- [ ] **Step 4: Update `_build_request_model` in `_usecase_generator.py`**

Replace the existing `_build_request_model` function (lines 121–139) with:

```python
def _build_request_model(
    fn_name: str,
    sig: inspect.Signature,
    docstring: str | None = None,
) -> tuple[type, _CoercionPlan]:
    """Build a flat Pydantic model; device params become str name fields.

    Enum and tuple annotations in primitive parameters are substituted with
    API-friendly equivalents.  A :class:`_CoercionPlan` records which
    parameters need coercion back to their original Python types at call time.

    :param fn_name: function name, used for the model class name
    :type fn_name: str
    :param sig: the function signature
    :type sig: inspect.Signature
    :param docstring: raw function docstring for Sphinx param extraction
    :type docstring: str | None
    :return: (Pydantic model, coercion plan)
    :rtype: tuple[type, _CoercionPlan]
    """
    fields: dict[str, Any] = {}
    coercions: dict[str, Any] = {}
    param_descriptions = _parse_sphinx_params(docstring)
    for name, param in sig.parameters.items():
        default = (
            param.default if param.default is not inspect.Parameter.empty else ...
        )
        if _classify_param(param.annotation) == "device":
            fields[name] = (str, ... if default is ... else default)
        else:
            annotation = param.annotation
            field_type = _annotation_to_field_type(annotation)
            if field_type is not annotation:
                coercions[name] = annotation
            desc = param_descriptions.get(name, "")
            if desc:
                fields[name] = (
                    field_type,
                    Field(default=default, description=desc),
                )
            else:
                fields[name] = (field_type, default)
    model_name = "".join(p.capitalize() for p in fn_name.split("_")) + "Request"
    return (
        create_model(model_name, **fields),  # type: ignore[call-overload]
        _CoercionPlan(coercions=coercions),
    )
```

- [ ] **Step 5: Update `_make_usecase_handler` to accept and apply `coercion_plan`**

Replace `_make_usecase_handler` (lines 142–222) with:

```python
def _make_usecase_handler(
    fn: Any,  # noqa: ANN401
    request_model: type,
    plans: list[_ParamPlan],
    coercion_plan: _CoercionPlan,
) -> Any:  # noqa: ANN401
    """Build an async handler that resolves device params then calls *fn*.

    Parameters in *coercion_plan* are translated from their API-friendly form
    (e.g. Enum member name strings) back to real Python types before *fn* is
    invoked.

    :param fn: the use-case function to invoke
    :type fn: Any
    :param request_model: Pydantic model for the request body
    :type request_model: type
    :param plans: per-parameter resolution plans
    :type plans: list[_ParamPlan]
    :param coercion_plan: parameters requiring type coercion before the call
    :type coercion_plan: _CoercionPlan
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
                raw = data[plan.name]
                orig_ann = coercion_plan.coercions.get(plan.name)
                kwargs[plan.name] = (
                    _coerce(raw, orig_ann) if orig_ann is not None else raw
                )
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
```

- [ ] **Step 6: Update `_plan_function` to pass docstring and thread coercion plan**

Replace `_plan_function` (lines 309–337) with:

```python
def _plan_function(  # pylint: disable=too-many-return-statements
    module_name: str,
    fn_name: str,
    fn: Any,  # noqa: ANN401
) -> SkippedMethod | tuple[type, list[_ParamPlan], _CoercionPlan]:
    """Validate a function and return its request model, param plans, and coercion plan.

    :param module_name: short module name for SkippedMethod records
    :type module_name: str
    :param fn_name: function name
    :type fn_name: str
    :param fn: the function object
    :type fn: Any
    :return: SkippedMethod when unroutable, else (request_model, plans, coercion_plan)
    :rtype: SkippedMethod | tuple[type, list[_ParamPlan], _CoercionPlan]
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

    request_model, coercion_plan = _build_request_model(
        fn_name, sig, fn.__doc__
    )
    return request_model, plans, coercion_plan
```

- [ ] **Step 7: Update `generate_usecase_routers` call site to unpack 3-tuple**

In `generate_usecase_routers`, replace:

```python
            request_model, plans = result
            handler = _make_usecase_handler(fn, request_model, plans)
```

with:

```python
            request_model, plans, coercion_plan = result
            handler = _make_usecase_handler(fn, request_model, plans, coercion_plan)
```

- [ ] **Step 8: Run tests**

```bash
pytest unittests/api/ -v
```

Expected: all tests pass.

- [ ] **Step 9: Run full lint**

```bash
nox -s lint
```

Fix any complaints.

- [ ] **Step 10: Commit**

```bash
git add boardfarm3/api/routers/_usecase_generator.py unittests/api/test_usecase_generator.py
git commit -m "feat(api): wire type coercion and field descriptions into use-case generator"
```

---

### Task 4: Integration smoke — verify multicast use-case routes

**Files:**
- Read: `boardfarm3/use_cases/multicast.py` (confirm `send_mldv2_report` annotation)
- Test: `unittests/api/test_usecase_generator.py`

**Interfaces:**
- Consumes from Task 3: `generate_usecase_routers`, coercion-aware `_plan_function`

- [ ] **Step 1: Inspect `send_mldv2_report` signature**

```bash
grep -n "send_mldv2_report\|MulticastGroupRecord\|McastSource\|McastGroup\|MulticastGroupRecordType" \
  boardfarm3/use_cases/multicast.py | head -30
```

Note the exact parameter name and annotation for the next step.

- [ ] **Step 2: Write smoke test confirming `send_mldv2_report` is routable**

Add to `unittests/api/test_usecase_generator.py` (adjust the import path if `multicast.py` lives elsewhere):

```python
def test_send_mldv2_report_is_routed_not_skipped() -> None:
    """send_mldv2_report must appear in routes, not in skipped-routes."""
    import importlib

    from boardfarm3.api.routers._usecase_generator import generate_usecase_routers

    mod = importlib.import_module("boardfarm3.use_cases.multicast")
    _, skipped = generate_usecase_routers([mod])
    skipped_names = [s.method for s in skipped]
    assert "send_mldv2_report" not in skipped_names, (
        f"send_mldv2_report was skipped: "
        + next(
            s.reason for s in skipped if s.method == "send_mldv2_report"
        )
    )
```

- [ ] **Step 3: Run the smoke test**

```bash
pytest unittests/api/test_usecase_generator.py::test_send_mldv2_report_is_routed_not_skipped -v
```

Expected: PASS.

If it fails with a reason like `"unroutable parameter: records"`, the annotation chain was not fully resolved. Debug by adding:

```python
from boardfarm3.api.routers._generator import _is_serialisable
import inspect, importlib
mod = importlib.import_module("boardfarm3.use_cases.multicast")
fn = getattr(mod, "send_mldv2_report")
sig = inspect.signature(fn, eval_str=True)
for name, param in sig.parameters.items():
    print(name, param.annotation, _is_serialisable(param.annotation))
```

- [ ] **Step 4: Run full test suite**

```bash
pytest unittests/ -v
```

Expected: all existing tests still pass.

- [ ] **Step 5: Run full lint**

```bash
nox -s lint
```

- [ ] **Step 6: Commit**

```bash
git add unittests/api/test_usecase_generator.py
git commit -m "test(api): smoke-verify send_mldv2_report is routed after type expansion"
```
