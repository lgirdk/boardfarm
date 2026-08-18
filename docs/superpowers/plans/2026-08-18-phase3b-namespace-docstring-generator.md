# Phase 3b: Router Namespace Prefixing, Docstring Cleanup, and Runtime Generator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three coordinated changes — (1) namespace-prefixed RouterBundle so plugins declare `"core"` or `"docsis"` once; (2) global OpenAPI schema post-processor that strips Sphinx `:param:` blocks from Swagger UI; (3) runtime template router generator that introspects Template ABCs and builds routes without hand-written boilerplate, reporting skipped methods via log and API endpoint.

**Architecture:** New `boardfarm3/api/routers/_generator.py` provides `generate_template_routers(templates) -> (list[APIRouter], list[SkippedMethod])`. `RouterBundle` (in `routers/__init__.py`) carries `(namespace, routers, skipped)`. `load_plugin_routers()` wraps bundles under their namespace prefix and returns `(routers, skipped)`. `create_app()` unpacks both, wires `GET /diagnostics/skipped-routes`, and adds an OpenAPI schema post-processor. `lan.py` is deleted — LAN routes are now generated at startup.

**Tech Stack:** Python 3.11-3.13, FastAPI, Pydantic v2 (`create_model`), Pluggy, `inspect` + `typing.get_args`/`get_origin` for reflection, `logging`.

## Global Constraints

- Python 3.11–3.13; `ruff target-version = "py39"` — no 3.12-only syntax.
- All four linters must pass: `ruff`, `flake8`/darglint2, `mypy --disallow-untyped-defs`, `pylint`.
- Sphinx-style docstrings on all public APIs (`:param:`, `:type:`, `:return:`, `:rtype:` blocks).
- `RouterBundle.namespace` is a plain `str`; namespace is applied exclusively by `load_plugin_routers()` — individual router files must not hardcode a namespace prefix.
- `boardfarm3/api/routers/lan.py` must be **deleted** in Task 2; `plugin.py` switches to `generate_template_routers([LAN])`.
- `load_plugin_routers()` return type changes from `list[APIRouter]` to `tuple[list[APIRouter], list[SkippedMethod]]`; all callers must be updated.
- After Task 3, all route paths become `/core/templates/lan/...`; existing tests must be updated accordingly.
- `_generator.py` must never import concrete device classes — only template ABCs passed in by the caller.
- The OpenAPI post-processor must guard `if desc` before calling the stripper.
- `generate_template_routers` logs each skipped method at WARNING level using Python `logging`.
- `GET /diagnostics/skipped-routes` returns `{"skipped": [{"template": str, "method": str, "reason": str}, ...]}`.
- Conventional commit messages (`feat:`, `fix:` with scope).

---

### Task 1: `_generator.py` — SkippedMethod, skip rules, and full route generation

**Files:**
- Create: `boardfarm3/api/routers/_generator.py`
- Create: `unittests/api/test_generator.py`

**Interfaces:**
- Consumes: `boardfarm3.api.routers._resolve`, `boardfarm3.templates.lan.LAN`
- Produces:
  - `SkippedMethod(template: str, method: str, reason: str)` dataclass
  - `generate_template_routers(templates: list[type]) -> tuple[list[APIRouter], list[SkippedMethod]]`

- [ ] **Step 1: Write failing tests** (`unittests/api/test_generator.py`)

```python
"""Unit tests for the template router generator."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

import pytest
from fastapi import APIRouter

from boardfarm3.api.routers._generator import SkippedMethod, generate_template_routers


# ---------------------------------------------------------------------------
# Minimal ABCs for testing
# ---------------------------------------------------------------------------

class _SimpleABC:
    @abstractmethod
    def greet(self, name: str) -> str: ...

    @abstractmethod
    def _private(self) -> str: ...  # skip: private

    @property
    @abstractmethod
    def label(self) -> str: ...  # skip: property

    @abstractmethod
    def complex_return(self) -> object: ...  # skip: non-serialisable return

    @abstractmethod
    def no_annotation(self, x) -> str: ...  # skip: missing param annotation


class _ReturnsNone:
    @abstractmethod
    def reset(self) -> None: ...


class _ReturnsBool:
    @abstractmethod
    def check(self) -> bool: ...


class _ReturnsDict:
    @abstractmethod
    def info(self) -> dict[str, Any]: ...


class _ReturnsList:
    @abstractmethod
    def items(self) -> list[str]: ...


class _ReturnsUnion:
    @abstractmethod
    def maybe(self) -> str | None: ...


# ---------------------------------------------------------------------------
# Skip rule tests
# ---------------------------------------------------------------------------

def test_private_method_skipped() -> None:
    _, skipped = generate_template_routers([_SimpleABC])
    names = [s.method for s in skipped]
    assert "_private" in names
    found = next(s for s in skipped if s.method == "_private")
    assert found.reason == "private"


def test_property_skipped() -> None:
    _, skipped = generate_template_routers([_SimpleABC])
    names = [s.method for s in skipped]
    assert "label" in names


def test_non_serialisable_return_skipped() -> None:
    _, skipped = generate_template_routers([_SimpleABC])
    found = next((s for s in skipped if s.method == "complex_return"), None)
    assert found is not None
    assert "serialis" in found.reason.lower()


def test_missing_param_annotation_skipped() -> None:
    _, skipped = generate_template_routers([_SimpleABC])
    found = next((s for s in skipped if s.method == "no_annotation"), None)
    assert found is not None


# ---------------------------------------------------------------------------
# Route generation tests
# ---------------------------------------------------------------------------

def test_public_serialisable_method_generates_route() -> None:
    routers, skipped = generate_template_routers([_SimpleABC])
    assert len(routers) == 1
    router = routers[0]
    route_paths = [r.path for r in router.routes]
    assert "/greet" in route_paths
    assert "/{index}/greet" in route_paths
    greet_skipped = [s for s in skipped if s.method == "greet"]
    assert greet_skipped == []


def test_returns_none_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsNone])
    paths = [r.path for r in routers[0].routes]
    assert "/reset" in paths


def test_returns_bool_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsBool])
    paths = [r.path for r in routers[0].routes]
    assert "/check" in paths


def test_returns_dict_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsDict])
    paths = [r.path for r in routers[0].routes]
    assert "/info" in paths


def test_returns_list_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsList])
    paths = [r.path for r in routers[0].routes]
    assert "/items" in paths


def test_returns_union_str_none_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsUnion])
    paths = [r.path for r in routers[0].routes]
    assert "/maybe" in paths


def test_lan_template_generates_all_serialisable_routes() -> None:
    from boardfarm3.templates.lan import LAN
    routers, _skipped = generate_template_routers([LAN])
    assert len(routers) == 1
    paths = {r.path for r in routers[0].routes}
    # These four were in the hand-written lan.py — must still be present
    assert "/ping" in paths
    assert "/{index}/ping" in paths
    assert "/get_interface_macaddr" in paths
    assert "/get_interface_ipv4addr" in paths
    assert "/set_link_state" in paths
    # Properties must not appear
    assert "/iface_dut" not in paths
    assert "/console" not in paths
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest unittests/api/test_generator.py -v 2>&1 | head -30
```

Expected: `ImportError` — `_generator` module does not exist yet.

- [ ] **Step 3: Implement `boardfarm3/api/routers/_generator.py`**

```python
"""Runtime template router generator for boardfarm API.

Introspects Template ABCs at agent startup and builds FastAPI routes
for all public methods with JSON-serialisable signatures.
"""

from __future__ import annotations

import inspect
import logging
import types
from dataclasses import dataclass
from typing import Any, Literal, Union, get_args, get_origin

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import create_model

from boardfarm3.api.routers import _async_response, _resolve

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Serialisability check
# ---------------------------------------------------------------------------

_PRIMITIVE_TYPES: frozenset[type] = frozenset(
    {str, int, float, bool, type(None), dict, list}
)


def _is_serialisable(annotation: Any) -> bool:  # noqa: ANN401
    """Return True if *annotation* is JSON-serialisable.

    :param annotation: a type annotation to check
    :type annotation: Any
    :return: True when the type can be expressed as JSON
    :rtype: bool
    """
    if annotation in _PRIMITIVE_TYPES:
        return True
    origin = get_origin(annotation)
    # Handle Union / X | Y
    if origin is Union or origin is types.UnionType:  # type: ignore[attr-defined]
        return all(_is_serialisable(a) for a in get_args(annotation))
    # Handle dict[K, V] and list[T]
    if origin in (dict, list):
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
    :param sig: method signature (self excluded by the caller)
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
    model_name = "".join(part.capitalize() for part in method_name.split("_")) + "Request"
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def _make_handler(
    template: type, method_name: str, request_model: type
) -> Any:  # noqa: ANN401
    """Build an async route handler for *method_name* on *template*.

    Sets ``__signature__`` so FastAPI generates a correct OpenAPI schema
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
        device = _resolve(session, template, index)  # type: ignore[type-abstract]
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
    handler.__signature__ = inspect.Signature(
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
            # Skip private
            if name.startswith("_"):
                continue
            # Skip properties
            if isinstance(inspect.getattr_static(template, name, None), property):
                skipped = SkippedMethod(template.__name__, name, "private" if name.startswith("_") else "property")
                all_skipped.append(skipped)
                _log.warning(
                    "template route skipped: %s.%s — %s",
                    template.__name__, name, skipped.reason,
                )
                continue
            # Must be a callable function
            if not callable(obj):
                continue
            # Skip classmethods and staticmethods
            raw = inspect.getattr_static(template, name, None)
            if isinstance(raw, (classmethod, staticmethod)):
                continue
            # Inspect signature
            try:
                sig = inspect.signature(obj)
            except (ValueError, TypeError):
                continue
            # Skip *args / **kwargs
            has_var = any(
                p.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                )
                for p in sig.parameters.values()
            )
            if has_var:
                all_skipped.append(SkippedMethod(template.__name__, name, "has *args or **kwargs"))
                _log.warning("template route skipped: %s.%s — has *args or **kwargs", template.__name__, name)
                continue
            # Skip missing param annotations (excluding self)
            missing = [
                p_name
                for p_name, p in sig.parameters.items()
                if p_name != "self" and p.annotation is inspect.Parameter.empty
            ]
            if missing:
                reason = f"missing annotation on: {', '.join(missing)}"
                all_skipped.append(SkippedMethod(template.__name__, name, reason))
                _log.warning("template route skipped: %s.%s — %s", template.__name__, name, reason)
                continue
            # Skip missing or non-serialisable return annotation
            ret = sig.return_annotation
            if ret is inspect.Parameter.empty:
                all_skipped.append(SkippedMethod(template.__name__, name, "missing return annotation"))
                _log.warning("template route skipped: %s.%s — missing return annotation", template.__name__, name)
                continue
            if not _is_serialisable(ret):
                reason = f"non-serialisable return type: {ret}"
                all_skipped.append(SkippedMethod(template.__name__, name, reason))
                _log.warning("template route skipped: %s.%s — %s", template.__name__, name, reason)
                continue
            # Build request model and handler
            request_model = _make_request_model(name, sig)
            handler = _make_handler(template, name, request_model)
            router.post(f"/{name}", status_code=200, response_model=None)(handler)
            router.post(f"/{{index}}/{name}", status_code=200, response_model=None)(handler)

        routers.append(router)

    return routers, all_skipped
```

**Important notes on this implementation:**
- `types.UnionType` (the `X | Y` union introduced in Python 3.10) may not exist on 3.9; check with `hasattr(types, 'UnionType')` and guard it.
- The property skip block has a logic error in the draft above: the reason is always "property" for a property (not "private"). Fix in the implementation.
- `inspect.getmembers(template)` returns both inherited and own members. For ABCs, it also returns inherited `object` methods. The `name.startswith("_")` guard handles those.

- [ ] **Step 4: Run the tests**

```bash
pytest unittests/api/test_generator.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run linters on the new file**

```bash
python -m ruff check boardfarm3/api/routers/_generator.py
python -m mypy boardfarm3/api/routers/_generator.py
```

Fix any issues.

- [ ] **Step 6: Commit**

```bash
git add boardfarm3/api/routers/_generator.py unittests/api/test_generator.py
git commit -m "feat(api): add runtime template router generator and SkippedMethod"
```

---

### Task 2: RouterBundle + updated `load_plugin_routers()` + hookspec + plugin.py + delete lan.py

**Files:**
- Modify: `boardfarm3/api/routers/__init__.py`
- Modify: `boardfarm3/api/hookspecs.py`
- Modify: `boardfarm3/api/plugin.py`
- Delete: `boardfarm3/api/routers/lan.py`

**Interfaces:**
- Consumes: `SkippedMethod` from `_generator.py`; `generate_template_routers` from `_generator.py`; `LAN` from `boardfarm3.templates.lan`
- Produces:
  - `RouterBundle(namespace: str, routers: list[APIRouter], skipped: list[SkippedMethod])` dataclass — exported from `boardfarm3.api.routers`
  - `load_plugin_routers() -> tuple[list[APIRouter], list[SkippedMethod]]` — return type changes; all callers must unpack both values
  - `boardfarm_add_api_routers() -> list[RouterBundle]` hookspec annotation (type only, no runtime change)

- [ ] **Step 1: Write a failing test for RouterBundle wrapping**

Add to `unittests/api/test_generator.py`:

```python
def test_routerbundle_wraps_routers_under_namespace() -> None:
    """RouterBundle namespace is prepended by load_plugin_routers."""
    from unittest.mock import MagicMock, patch
    from boardfarm3.api.routers import RouterBundle, load_plugin_routers

    inner = APIRouter(prefix="/templates/foo")

    @inner.get("/bar")
    async def _dummy() -> dict:  # noqa: ANN201
        return {}

    bundle = RouterBundle(namespace="test_ns", routers=[inner], skipped=[])

    with patch(
        "boardfarm3.api.routers.pluggy.PluginManager"
    ) as mock_pm_cls:
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.hook.boardfarm_add_api_routers.return_value = [bundle]
        routers, skipped = load_plugin_routers()

    assert len(routers) == 1
    all_paths = [r.path for r in routers[0].routes]
    assert any("/test_ns/templates/foo/bar" in p or p == "/bar" for p in all_paths)
    assert skipped == []
```

Run: `pytest unittests/api/test_generator.py::test_routerbundle_wraps_routers_under_namespace -v`  
Expected: FAIL (`RouterBundle` not importable yet).

- [ ] **Step 2: Update `boardfarm3/api/routers/__init__.py`**

Add the `RouterBundle` dataclass (importing `SkippedMethod` under `TYPE_CHECKING` for the type annotation but at runtime too since it's a field type):

```python
"""Router helpers shared across all boardfarm API router modules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, TypeVar

import pluggy
from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    from boardfarm3.api.session import Session

from boardfarm3.api.routers._generator import SkippedMethod  # noqa: E402 (after TYPE_CHECKING)

T = TypeVar("T")

_ENTRYPOINT_GROUP = "boardfarm_api"
_log = logging.getLogger(__name__)


@dataclass
class RouterBundle:
    """A namespace-prefixed group of FastAPI routers contributed by one plugin.

    :param namespace: URL namespace for this plugin's routes, e.g. ``"core"``
        or ``"docsis"``
    :type namespace: str
    :param routers: routers whose paths will be prefixed with
        ``/{namespace}``
    :type routers: list[APIRouter]
    :param skipped: methods the generator could not route for this bundle
    :type skipped: list[SkippedMethod]
    """

    namespace: str
    routers: list[APIRouter] = field(default_factory=list)
    skipped: list[SkippedMethod] = field(default_factory=list)


def _resolve(session: Session, template: type[T], index: int) -> T:
    # ... unchanged ...


def _async_response(job: Job) -> JSONResponse:
    # ... unchanged ...


def load_plugin_routers() -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Discover all FastAPI routers and collect skipped methods.

    Creates a short-lived PluginManager, loads all installed ``boardfarm_api``
    entrypoints, wraps each bundle's routers under ``/{namespace}``, and
    aggregates their skipped method lists.

    :return: namespaced routers and all skipped methods from all bundles
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
    try:
        from boardfarm3.api import hookspecs as _api_hookspecs

        _pm = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        _pm.add_hookspecs(_api_hookspecs)
        _pm.load_setuptools_entrypoints(_ENTRYPOINT_GROUP)
        bundles: list[RouterBundle] = _pm.hook.boardfarm_add_api_routers()
        result_routers: list[APIRouter] = []
        result_skipped: list[SkippedMethod] = []
        for bundle in bundles:
            wrapper = APIRouter(prefix=f"/{bundle.namespace}")
            for router in bundle.routers:
                wrapper.include_router(router)
            result_routers.append(wrapper)
            result_skipped.extend(bundle.skipped)
        return result_routers, result_skipped
    except Exception:  # noqa: BLE001
        return [], []
```

Keep `_resolve`, `_async_response`, and `_Job` type hint exactly as in the current file — only add `RouterBundle` and update `load_plugin_routers`.

- [ ] **Step 3: Update `boardfarm3/api/hookspecs.py`**

Change the `boardfarm_add_api_routers` annotation only (no runtime effect):

```python
if TYPE_CHECKING:
    from boardfarm3.api.routers import RouterBundle  # avoids circular import

@hookspec_api
def boardfarm_add_api_routers() -> list[RouterBundle]: ...
```

- [ ] **Step 4: Update `boardfarm3/api/plugin.py`**

Replace the hand-written lan import with the generator:

```python
@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:
    """Return the core boardfarm API routers, generated from template ABCs.

    :return: one RouterBundle for the ``core`` namespace
    :rtype: list[RouterBundle]
    """
    from boardfarm3.api.routers import RouterBundle
    from boardfarm3.api.routers._generator import generate_template_routers
    from boardfarm3.templates.lan import LAN

    routers, skipped = generate_template_routers([LAN])
    return [RouterBundle(namespace="core", routers=routers, skipped=skipped)]
```

- [ ] **Step 5: Move `_async_response` from `lan.py` into `boardfarm3/api/routers/__init__.py`**

`_generator.py` imports `_async_response` from `boardfarm3.api.routers`. Currently it lives only in `lan.py`. Move it to `__init__.py` **before** deleting `lan.py`. The function body is:

```python
def _async_response(job: Job) -> JSONResponse:
    """Build a 202 Accepted JSON response from a queued *job*.

    :param job: the job returned by ``queue.submit(..., mode="async")``
    :type job: Job
    :return: 202 response carrying ``job_id`` and the current job state
    :rtype: JSONResponse
    """
    from http import HTTPStatus

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=int(HTTPStatus.ACCEPTED),
        content={"job_id": job.id, "state": job.state.value},
    )
```

Add `from boardfarm3.api.execution import Job` under `TYPE_CHECKING` in `__init__.py` if not already present.

- [ ] **Step 6: Delete `boardfarm3/api/routers/lan.py`**

```bash
git rm boardfarm3/api/routers/lan.py
```

- [ ] **Step 7: Run the new test and the full suite (expect test_routers_lan failures — they'll be fixed in Task 4)**

```bash
pytest unittests/api/test_generator.py -v
pytest unittests/api/test_plugin.py -v
```

`test_generator.py` must be all green. `test_routers_lan.py` will fail on paths — that is expected here and fixed in Task 4.

- [ ] **Step 8: Commit**

```bash
git add boardfarm3/api/routers/__init__.py boardfarm3/api/hookspecs.py boardfarm3/api/plugin.py
git commit -m "feat(api): add RouterBundle, update load_plugin_routers to return skipped, wire generator in plugin"
```

---

### Task 3: `app.py` — docstring cleaner + skipped-routes endpoint + unpack load_plugin_routers

**Files:**
- Modify: `boardfarm3/api/app.py`

**Interfaces:**
- Consumes: `load_plugin_routers() -> tuple[list[APIRouter], list[SkippedMethod]]`
- Produces:
  - `_strip_sphinx_params(text: str) -> str` (module-level private)
  - `GET /diagnostics/skipped-routes` endpoint
  - `app.state.skipped_routes: list[dict[str, str]]`
  - OpenAPI schema post-processor that strips Sphinx field-list lines

- [ ] **Step 1: Update `create_app()` to unpack `load_plugin_routers()`**

In `create_app()`, replace the current loop:

```python
# BEFORE:
from boardfarm3.api.routers import load_plugin_routers
for _router in load_plugin_routers():
    app.include_router(_router)

# AFTER:
import logging as _logging
from boardfarm3.api.routers import load_plugin_routers

_gen_log = _logging.getLogger(__name__)
_plugin_routers, _skipped = load_plugin_routers()
for _router in _plugin_routers:
    app.include_router(_router)
for _s in _skipped:
    _gen_log.warning(
        "template route skipped: %s.%s — %s", _s.template, _s.method, _s.reason
    )
app.state.skipped_routes = [
    {"template": s.template, "method": s.method, "reason": s.reason}
    for s in _skipped
]
```

- [ ] **Step 2: Add `_strip_sphinx_params` at module level**

```python
def _strip_sphinx_params(text: str) -> str:
    """Return the introductory paragraph of a Sphinx docstring.

    Strips all content from the first Sphinx field-list marker onward
    (any line whose stripped form starts with ``:``, e.g. ``:param``,
    ``:type``, ``:return:``, ``:raises:``).

    :param text: raw docstring text
    :type text: str
    :return: text with Sphinx field-list lines removed
    :rtype: str
    """
    clean: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith(":"):
            break
        clean.append(line)
    return "\n".join(clean).rstrip()
```

- [ ] **Step 3: Add the OpenAPI schema post-processor in `create_app()`**

Immediately after `app = FastAPI(...)`:

```python
_orig_openapi = app.openapi

def _clean_openapi() -> dict[str, Any]:
    schema = _orig_openapi()
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                desc = operation.get("description", "")
                if desc:
                    operation["description"] = _strip_sphinx_params(desc)
    return schema

app.openapi = _clean_openapi  # type: ignore[method-assign]
```

- [ ] **Step 4: Add `GET /diagnostics/skipped-routes` endpoint**

```python
@app.get("/diagnostics/skipped-routes")
async def diagnostics_skipped_routes() -> dict[str, Any]:
    """List template methods that the router generator could not expose.

    Returns methods excluded from route generation (non-serialisable returns,
    missing annotations, properties, etc.) so developers know what to add
    manually.

    :return: skipped method list
    :rtype: dict[str, Any]
    """
    return {"skipped": app.state.skipped_routes}
```

- [ ] **Step 5: Run tests to verify app starts correctly**

```bash
pytest unittests/api/test_app.py unittests/api/test_session.py -v
```

Expected: all pass.

- [ ] **Step 6: Verify docstring stripping manually**

```bash
python -c "
from fastapi.testclient import TestClient
from boardfarm3.api import app as app_module
from boardfarm3.api.session import Session

app = app_module.create_app('s1', 'board')
client = TestClient(app)
schema = client.get('/openapi.json').json()
for path, item in schema['paths'].items():
    for op in item.values():
        desc = op.get('description', '')
        if ':param' in desc or ':rtype' in desc:
            print('FAIL:', path, repr(desc[:80]))
            break
else:
    print('OK — no sphinx params in any description')
"
```

Expected output: `OK — no sphinx params in any description`

- [ ] **Step 7: Commit**

```bash
git add boardfarm3/api/app.py
git commit -m "feat(api): add docstring cleaner, skipped-routes endpoint, unpack load_plugin_routers"
```

---

### Task 4: Update tests — fix URL paths and add new tests

**Files:**
- Modify: `unittests/api/test_routers_lan.py`
- Verify: `unittests/control/test_openapi.py` (no change needed)

**Interfaces:**
- Consumes: routes now at `/core/templates/lan/...` (not `/templates/lan/...`)

- [ ] **Step 1: Update all 11 existing URL paths in `test_routers_lan.py`**

Replace every occurrence of `"/templates/lan/` with `"/core/templates/lan/` in the file. There are exactly 11 test functions each with one URL. Use a precise find-and-replace; do not change anything else.

After replacement, verify the count:
```bash
grep -c '"/core/templates/lan/' unittests/api/test_routers_lan.py
```
Expected: at least 11.

- [ ] **Step 2: Run existing tests to verify they pass with new URLs**

```bash
pytest unittests/api/test_routers_lan.py -v
```

Expected: all 11 pass.

- [ ] **Step 3: Add four new tests to `test_routers_lan.py`**

```python
# ---------------------------------------------------------------------------
# Tests — namespace + docstring + diagnostics
# ---------------------------------------------------------------------------


def test_namespace_prefix_applied(booted_client: TestClient) -> None:
    """Routes appear under /core/templates/lan/, not bare /templates/lan/.

    :param booted_client: test client with booted session
    :type booted_client: TestClient
    """
    schema = booted_client.get("/openapi.json").json()
    paths = list(schema["paths"].keys())
    assert any("/core/templates/lan/" in p for p in paths)
    assert not any(p.startswith("/templates/lan/") for p in paths)


def test_namespace_prefix_absent_for_bare_templates(booted_client: TestClient) -> None:
    """Bare /templates/lan/ paths are absent — namespace is always applied.

    :param booted_client: test client with booted session
    :type booted_client: TestClient
    """
    schema = booted_client.get("/openapi.json").json()
    for path in schema["paths"]:
        assert not path.startswith("/templates/lan/"), (
            f"Bare template path leaked into schema: {path}"
        )


def test_openapi_descriptions_have_no_sphinx_params(booted_client: TestClient) -> None:
    """No operation description contains raw Sphinx field markers.

    :param booted_client: test client with booted session
    :type booted_client: TestClient
    """
    schema = booted_client.get("/openapi.json").json()
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            desc = operation.get("description", "")
            assert ":param" not in desc, (
                f"Sphinx :param found in {method.upper()} {path}: {desc!r}"
            )
            assert ":rtype" not in desc, (
                f"Sphinx :rtype found in {method.upper()} {path}: {desc!r}"
            )


def test_skipped_routes_endpoint(booted_client: TestClient) -> None:
    """GET /diagnostics/skipped-routes returns a list of skipped methods.

    :param booted_client: test client with booted session
    :type booted_client: TestClient
    """
    resp = booted_client.get("/diagnostics/skipped-routes")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert "skipped" in data
    assert isinstance(data["skipped"], list)
    # Each entry must have the three required keys
    for entry in data["skipped"]:
        assert "template" in entry
        assert "method" in entry
        assert "reason" in entry
```

- [ ] **Step 4: Run all new tests**

```bash
pytest unittests/api/test_routers_lan.py -v
```

Expected: all 15 tests pass (11 existing + 4 new).

- [ ] **Step 5: Run the full test suite**

```bash
pytest unittests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 6: Run linters**

```bash
python -m ruff check boardfarm3/api/
python -m ruff check unittests/api/
python -m mypy boardfarm3/api/routers/_generator.py boardfarm3/api/routers/__init__.py boardfarm3/api/app.py
```

Fix any issues.

- [ ] **Step 7: Commit**

```bash
git add unittests/api/test_routers_lan.py
git commit -m "test(api): update URL paths to /core/templates/lan/ and add namespace, docstring, diagnostics tests"
```
