# Generator Type Expansion & API Description Enrichment

**Date:** 2026-08-19
**Scope:** `boardfarm3/api/routers/_generator.py`, `boardfarm3/api/routers/_usecase_generator.py`, `boardfarm3/api/app.py`

## Problem

Two independent gaps in the runtime router generators reduce the number of usable API endpoints and degrade the Swagger UI experience:

1. **Type coverage:** `_is_serialisable` only accepts bare primitives, `list`, `dict`, and Unions thereof. `tuple`, `Enum` subclasses, and `TypedDict` definitions are classified as `"unroutable"`, causing otherwise-callable methods to appear only at `/diagnostics/skipped-routes`. Real-world examples: `MulticastGroupRecord = list[tuple[list[str], str, MulticastGroupRecordType]]` (multicast use-case), `TypedDict`-typed DHCP parameters.

2. **API descriptions:** Operation descriptions are either synthetic one-liners (template routes) or the first line of the function docstring (use-case routes). Request body fields carry no description text. Users opening Swagger UI cannot tell what to pass without reading source code.

## Goals

- Expand `_is_serialisable` to accept `tuple`, `Enum` subclasses, and `TypedDict`.
- Convert Enum parameters to `Literal[member_names]` in the Pydantic model; translate back to the real Enum before invoking boardfarm methods.
- Convert `tuple` parameters to `list` in the Pydantic model; coerce back to `tuple` at call time.
- Extract `:param name: description` from Sphinx docstrings and inject into `Field(description=...)` on each Pydantic request-body field.
- Preserve the existing skip-and-report safety net for annotations that are still unresolvable.

## Non-goals

- `set` / `frozenset` — no JSON equivalent; remain skipped.
- Arbitrary class instances or Pydantic models from external packages — remain skipped.
- Changing the operation-level description format in `app.py` — `_strip_sphinx_params` stays as-is.
- Generating nested Pydantic `BaseModel` subclasses for `TypedDict` (future work).

---

## Design

### Section 1 — Type System Expansion (`_is_serialisable`)

Three new cases added to `_is_serialisable` in `_generator.py`, evaluated before the final `return False`:

**`tuple`**
```python
if get_origin(annotation) is tuple:
    args = get_args(annotation)
    if args and args[-1] is Ellipsis:
        return _is_serialisable(args[0])      # tuple[str, ...] — uniform element type
    return all(_is_serialisable(a) for a in args)
```

**`Enum` subclasses**
```python
if isinstance(annotation, type) and issubclass(annotation, Enum):
    return True   # serialised as Literal of member names
```

**`TypedDict`**
```python
if isinstance(annotation, type) and hasattr(annotation, '__annotations__') and hasattr(annotation, '__total__'):
    return all(_is_serialisable(v) for v in annotation.__annotations__.values())
```

`_classify_param` in `_usecase_generator.py` requires no change — it delegates to `_is_serialisable`, so the new cases automatically become `"primitive"`.

---

### Section 2 — Pydantic Model Generation & Coercion Plan

#### `_annotation_to_field_type(annotation)`

New helper in `_generator.py`. Walks the annotation tree and substitutes API-friendly equivalents for Enum and tuple:

| Original | Pydantic field type |
|---|---|
| `EnumClass` | `Literal[("NAME_A", "NAME_B", ...)]` |
| `tuple[X, Y, Z]` | `list[X' \| Y' \| Z']` (args substituted recursively) |
| `tuple[str, ...]` | `list[str]` |
| `list[tuple[...]]` | `list[list[...]]` (inner substitution) |
| `TypedDict` | `dict` (pass-through; structure validated by `_is_serialisable`) |
| primitives | unchanged |

Substitution is recursive — `list[tuple[str, EnumClass]]` becomes `list[list[str \| Literal[...]]]`.

#### `_CoercionPlan` dataclass

Added to `_generator.py`, imported by `_usecase_generator.py`:

```python
@dataclass
class _CoercionPlan:
    coercions: dict[str, Any]  # {param_name: original_annotation}
```

Built in `_make_request_model` / `_build_request_model` alongside the Pydantic model. Only parameters whose `_annotation_to_field_type` substitution produces a type different from the original get an entry. Parameters that are already primitive pass through with zero overhead.

#### `_coerce(value, annotation)` recursive function

Added to `_generator.py`:

```python
def _coerce(value: Any, ann: Any) -> Any:
    if isinstance(ann, type) and issubclass(ann, Enum):
        return ann[value]                           # name → Enum member
    origin = get_origin(ann)
    args = get_args(ann)
    if origin is tuple:
        if args and args[-1] is Ellipsis:
            return tuple(_coerce(v, args[0]) for v in value)
        return tuple(_coerce(v, a) for v, a in zip(value, args))
    if origin is list and args:
        return [_coerce(v, args[0]) for v in value]
    return value                                    # TypedDict, primitive — pass-through
```

#### Handler change (both generators)

One block inserted between `body.model_dump()` and the actual boardfarm call:

```python
kwargs = body.model_dump()
for param_name, original_ann in coercion_plan.coercions.items():
    if param_name in kwargs:
        kwargs[param_name] = _coerce(kwargs[param_name], original_ann)
result = await asyncio.to_thread(target_fn, **kwargs)
```

The `coercion_plan` is captured in the handler closure at route-registration time. No changes to boardfarm template methods or use-case functions.

---

### Section 3 — Sphinx Description Extraction

#### `_parse_sphinx_params(docstring)` helper

Added to `_generator.py`, imported by `_usecase_generator.py`:

```python
_SPHINX_PARAM_RE = re.compile(
    r":param\s+(\w+):\s*(.+?)(?=\n\s*:|$)", re.DOTALL
)

def _parse_sphinx_params(docstring: str | None) -> dict[str, str]:
    if not docstring:
        return {}
    return {
        m.group(1): " ".join(m.group(2).split())
        for m in _SPHINX_PARAM_RE.finditer(docstring)
    }
```

Returns `{param_name: description_text}` with internal whitespace collapsed to a single space.

#### Field description injection

In both `_make_request_model` (template generator) and `_build_request_model` (use-case generator), `param_descriptions` is built from `_parse_sphinx_params(obj.__doc__)` (template: `obj` is already in scope in `_process_member`) or `_parse_sphinx_params(fn.__doc__)` (use-case).

Each field in the `create_model()` call becomes:

```python
desc = param_descriptions.get(name, "")
fields[name] = (field_type, Field(default=..., description=desc))
```

Parameters with no matching `:param:` entry get an empty description — no regression from current behaviour.

#### `app.py` — no change

`_strip_sphinx_params` keeps stripping the Sphinx block from the operation-level description. The two layers are independent:

- **Operation description** = clean prose summary (unchanged)
- **Each request body field** = inline description from `:param:` (new)

---

## Affected Files

| File | Change |
|---|---|
| `boardfarm3/api/routers/_generator.py` | Add `tuple`/`Enum`/`TypedDict` to `_is_serialisable`; add `_annotation_to_field_type`, `_CoercionPlan`, `_coerce`, `_parse_sphinx_params`; update `_make_request_model` and handler |
| `boardfarm3/api/routers/_usecase_generator.py` | Import new helpers; update `_build_request_model` and handler |
| `boardfarm3/api/app.py` | No change |

## Testing

- Unit tests in `unittests/api/` for `_is_serialisable` (new cases), `_annotation_to_field_type`, `_coerce`, `_parse_sphinx_params`.
- Integration smoke: `send_mldv2_report` and at least one DHCP TypedDict use-case must appear in the generated routes (not in `/diagnostics/skipped-routes`).
- Regression: existing skipped routes must still be skipped; existing passing routes must not change behaviour.
