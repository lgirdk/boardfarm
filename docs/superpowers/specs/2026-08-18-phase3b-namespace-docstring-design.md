# Phase 3b: Router Namespace Prefixing, OpenAPI Docstring Cleanup, and Runtime Template Router Generator

## Goal

Three coordinated improvements to the boardfarm API layer:

1. **RouterBundle** — plugins declare a namespace once; all their routers are automatically prefixed (e.g., `core/templates/lan/ping`, `docsis/templates/wan/ping`).
2. **OpenAPI docstring cleaner** — global schema post-processor strips Sphinx `:param:`/`:return:` blocks from Swagger UI descriptions.
3. **Runtime template router generator** — introspects Template ABCs at agent startup, dynamically builds routes for all public serializable methods, and reports which methods were skipped (with reason) both in the startup log and via a diagnostics endpoint.

## Architecture

Three independent mechanisms; together they eliminate all hand-written router boilerplate for the common case:

1. **RouterBundle** — thin dataclass `(namespace: str, routers: list[APIRouter])`. `load_plugin_routers()` wraps each bundle's routers under `/{namespace}` before handing to `create_app()`. Individual router files remain unchanged (or are deleted once the generator covers them).

2. **Schema post-processor** — closure that wraps `app.openapi` after `FastAPI(...)` construction. Strips Sphinx field-list lines from every operation description. Runs once per process (FastAPI caches the schema).

3. **Generator** — `generate_template_routers(templates) -> (list[APIRouter], list[SkippedMethod])` in `boardfarm3/api/routers/_generator.py`. For each template ABC, reflects over public instance methods, applies skip rules, builds a `pydantic.create_model`-based request model and a dynamic route handler (with `__signature__` set for FastAPI introspection), and emits WARNING-level logs for every skipped method. The skipped list is stored on `app.state` and served by `GET /diagnostics/skipped-routes`.

## Tech Stack

- Python 3.11–3.13
- FastAPI / Starlette (`APIRouter.include_router` for namespace wrapping; `__signature__` injection for dynamic handlers)
- Pluggy (hookspec return type annotation update only)
- Pydantic v2 (`create_model` for dynamic request models)
- `inspect` stdlib (method reflection, signature introspection)
- `typing.get_type_hints` (resolve forward references for return-type serialisability check)

## Global Constraints

- Python target: 3.11–3.13; `ruff target-version = "py39"` — no 3.12-only syntax.
- All four linters must pass: `ruff`, `flake8`/darglint2, `mypy --disallow-untyped-defs`, `pylint`.
- Sphinx-style docstrings on all public APIs.
- `RouterBundle.namespace` is a plain `str`; no URL-encoding or validation — plugin authors own correctness.
- Individual router files must not set a namespace prefix — that is `load_plugin_routers()`'s exclusive responsibility.
- The hookspec `boardfarm_add_api_routers()` return type changes from `list[APIRouter]` to `list[RouterBundle]`; hookspec annotation and all hookimpls must match.
- The post-processor must guard `if desc` before calling the stripper.
- `_generator.py` must never import concrete device classes — only template ABCs passed in by the caller.
- `generate_template_routers` is pure (no side effects beyond WARNING logs); the caller stores and exposes the skipped list.
- After this phase, `boardfarm3/api/routers/lan.py` is deleted and replaced by generator output. The `plugin.py` hookimpl switches to `generate_template_routers([LAN])`.
- All existing 11 `test_routers_lan.py` tests must pass with updated URL paths (`/core/templates/lan/...`).
- Conventional commit messages (`feat:`, `fix:` with scope).

---

## Section 1: RouterBundle

### Dataclass (`boardfarm3/api/routers/__init__.py`)

```python
from dataclasses import dataclass, field
from fastapi import APIRouter

@dataclass
class RouterBundle:
    """A namespace-prefixed group of FastAPI routers contributed by one plugin.

    :param namespace: URL namespace for this plugin's routes, e.g. ``"core"``
        or ``"docsis"``
    :type namespace: str
    :param routers: routers whose paths will be prefixed with
        ``/{namespace}``
    :type routers: list[APIRouter]
    :param skipped: methods skipped by the generator for this bundle
        (empty when routers are written manually)
    :type skipped: list[SkippedMethod]
    """
    namespace: str
    routers: list[APIRouter] = field(default_factory=list)
    skipped: list[SkippedMethod] = field(default_factory=list)
```

### Updated `load_plugin_routers()`

Return type changes to `tuple[list[APIRouter], list[SkippedMethod]]` so `create_app()` can store the skipped list without a second reflection pass:

```python
def load_plugin_routers() -> tuple[list[APIRouter], list[SkippedMethod]]:
    try:
        import pluggy
        from boardfarm3.api import hookspecs as _api_hookspecs

        _pm = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        _pm.add_hookspecs(_api_hookspecs)
        _pm.load_setuptools_entrypoints(_ENTRYPOINT_GROUP)
        bundles: list[RouterBundle] = _pm.hook.boardfarm_add_api_routers()
        routers: list[APIRouter] = []
        skipped: list[SkippedMethod] = []
        for bundle in bundles:
            wrapper = APIRouter(prefix=f"/{bundle.namespace}")
            for router in bundle.routers:
                wrapper.include_router(router)
            routers.append(wrapper)
            skipped.extend(bundle.skipped)
        return routers, skipped
    except Exception:  # noqa: BLE001
        return [], []
```

`app.py` unpacks both: `_routers, _skipped = load_plugin_routers()`. The include-router loop and diagnostics wiring both use the single call result.

### Hookspec annotation (`boardfarm3/api/hookspecs.py`)

```python
if TYPE_CHECKING:
    from boardfarm3.api.routers import RouterBundle  # avoid circular at runtime

@hookspec_api
def boardfarm_add_api_routers() -> list[RouterBundle]: ...
```

### Plugin hookimpl (`boardfarm3/api/plugin.py`)

After this phase `lan.py` is deleted; the hookimpl switches to the generator:

```python
@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:
    from boardfarm3.api.routers import RouterBundle
    from boardfarm3.api.routers._generator import generate_template_routers
    from boardfarm3.templates.lan import LAN
    routers, skipped = generate_template_routers([LAN])
    return [RouterBundle(namespace="core", routers=routers, skipped=skipped)]
```

`skipped` is carried on the bundle so `load_plugin_routers()` can surface it to `create_app()` without a second reflection pass.

### URL changes

| Before | After |
|--------|-------|
| `/templates/lan/ping` | `/core/templates/lan/ping` |
| `/templates/lan/{index}/ping` | `/core/templates/lan/{index}/ping` |
| `/templates/lan/get_interface_macaddr` | `/core/templates/lan/get_interface_macaddr` |
| `/templates/lan/{index}/get_interface_macaddr` | `/core/templates/lan/{index}/get_interface_macaddr` |
| `/templates/lan/get_interface_ipv4addr` | `/core/templates/lan/get_interface_ipv4addr` |
| `/templates/lan/{index}/get_interface_ipv4addr` | `/core/templates/lan/{index}/get_interface_ipv4addr` |
| `/templates/lan/set_link_state` | `/core/templates/lan/set_link_state` |
| `/templates/lan/{index}/set_link_state` | `/core/templates/lan/{index}/set_link_state` |

---

## Section 2: Sphinx Docstring Post-Processor

### Stripper function (`boardfarm3/api/app.py`, module-level private)

```python
def _strip_sphinx_params(text: str) -> str:
    """Return the introductory paragraph of a Sphinx docstring.

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

### Schema wrapper (immediately after `app = FastAPI(...)` in `create_app()`)

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

---

## Section 3: Runtime Template Router Generator

### New file: `boardfarm3/api/routers/_generator.py`

#### Skip rules

A method is **skipped** (not turned into a route) if any of the following apply:

| Rule | Reason logged |
|------|---------------|
| Name starts with `_` | private |
| Is a `property` | not callable as a route |
| Is a `classmethod` or `staticmethod` | not instance method |
| Has `*args` or `**kwargs` in signature | cannot map to Pydantic model |
| Any parameter (excluding `self`) lacks a type annotation | schema generation impossible |
| Return type annotation is absent | cannot determine serialisability |
| Return type is not JSON-serialisable (see below) | non-serialisable return |

**JSON-serialisable return types** (exact check on the unwrapped annotation):
`type(None)`, `str`, `int`, `float`, `bool`, `dict`, `list`, and their `typing` generic forms (`dict[str, Any]`, `list[str]`, etc.). Anything else is skipped.

#### `SkippedMethod` dataclass

```python
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
```

#### `generate_template_routers` signature

```python
def generate_template_routers(
    templates: list[type],
) -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Generate FastAPI routers for each template ABC.

    Reflects over public instance methods on each template, applies skip
    rules, and builds a route handler for each accepted method.  Methods
    that cannot be represented as a route are collected in the returned
    skipped list and logged at WARNING level.

    :param templates: template ABC classes to introspect
    :type templates: list[type]
    :return: generated routers and list of skipped methods
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
```

#### Dynamic request model

For each accepted method, a Pydantic model is built at runtime:

```python
from pydantic import create_model

fields = {
    name: (annotation, default_or_ellipsis)
    for name, param in sig.parameters.items()
    if name != "self"
}
RequestModel = create_model(f"{MethodNameInCamelCase}Request", **fields)
```

#### Dynamic route handler

```python
import inspect
from typing import Any, Literal

from fastapi import Request
from fastapi.responses import JSONResponse

def _make_handler(template: type, method_name: str, RequestModel: type) -> Any:
    async def handler(
        request: Request,
        body: RequestModel,
        index: int = 0,
        mode: Literal["sync", "async"] = "sync",
    ) -> dict[str, Any] | JSONResponse:
        session = request.app.state.session
        device = _resolve(session, template, index)
        job = await session.queue.submit(
            lambda: getattr(device, method_name)(**body.model_dump()),
            mode=mode,
        )
        if mode == "async":
            return _async_response(job)
        return {"result": job.result}

    # Inject concrete signature so FastAPI generates correct OpenAPI schema.
    handler.__signature__ = inspect.Signature([
        inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          annotation=Request),
        inspect.Parameter("body", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          annotation=RequestModel),
        inspect.Parameter("index", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          default=0, annotation=int),
        inspect.Parameter("mode", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          default="sync", annotation=Literal["sync", "async"]),
    ])
    handler.__name__ = f"{template.__name__.lower()}_{method_name}"
    handler.__doc__ = f"{method_name.replace('_', ' ').capitalize()} on {template.__name__} device at *index*."
    return handler
```

Each accepted method registers two routes (shorthand + indexed):

```python
router.post(f"/{method_name}", status_code=200, response_model=None)(handler)
router.post(f"/{{index}}/{method_name}", status_code=200, response_model=None)(handler)
```

### Skipped-methods report in `create_app()` (`boardfarm3/api/app.py`)

`load_plugin_routers()` now returns `(routers, skipped)`. `create_app()` unpacks both in one call:

```python
import logging as _logging
_gen_logger = _logging.getLogger(__name__)

from boardfarm3.api.routers import load_plugin_routers
_routers, _skipped = load_plugin_routers()
for _router in _routers:
    app.include_router(_router)
for s in _skipped:
    _gen_logger.warning(
        "template route skipped: %s.%s — %s", s.template, s.method, s.reason
    )
app.state.skipped_routes = [
    {"template": s.template, "method": s.method, "reason": s.reason}
    for s in _skipped
]
```

**`GET /diagnostics/skipped-routes` endpoint** (added in `create_app()`):

```python
@app.get("/diagnostics/skipped-routes")
async def skipped_routes() -> dict[str, Any]:
    return {"skipped": app.state.skipped_routes}
```

---

## Section 4: Tests

### `unittests/api/test_routers_lan.py`

All 11 existing tests update URL paths from `/templates/lan/...` to `/core/templates/lan/...`.

New tests added to the same file:

- `test_namespace_prefix_applied` — asserts `/core/templates/lan/ping` appears in OpenAPI schema; asserts bare `/templates/lan/ping` is absent.
- `test_routerbundle_wraps_multiple_routers` — two `APIRouter` objects with different prefixes wrapped in one `RouterBundle("ns", [...])`, verify both paths appear under `/ns/`.
- `test_openapi_description_no_sphinx_params` — iterates all operation descriptions in `/openapi.json`, asserts none contain `:param` or `:rtype`.
- `test_skipped_routes_endpoint_returns_list` — `GET /diagnostics/skipped-routes` returns `{"skipped": [...]}` (empty or populated).

### `unittests/api/test_generator.py` (new file)

- `test_public_serialisable_method_generates_route` — a minimal ABC with one annotated `-> str` method; assert the router has two paths for it.
- `test_private_method_skipped` — method starting with `_` produces a `SkippedMethod(reason="private")`.
- `test_property_skipped` — `@property` method is skipped.
- `test_non_serialisable_return_skipped` — method returning a custom class produces `SkippedMethod(reason="non-serialisable return")`.
- `test_missing_annotation_skipped` — unannotated parameter produces a `SkippedMethod`.
- `test_lan_template_generates_four_routes` — `generate_template_routers([LAN])` returns an `APIRouter` with 8 paths (4 methods × 2 variants) and an empty skipped list.

### `unittests/control/test_openapi.py`

No changes needed — path prefix assertion already uses `all(p.startswith("/sessions/{session_id}/") ...)`.

---

## File Summary

| Action | File |
|--------|------|
| Modify | `boardfarm3/api/routers/__init__.py` — add `RouterBundle`, update `load_plugin_routers()` |
| Create | `boardfarm3/api/routers/_generator.py` — `SkippedMethod`, `generate_template_routers` |
| Delete | `boardfarm3/api/routers/lan.py` — replaced by generator |
| Modify | `boardfarm3/api/hookspecs.py` — update return type annotation |
| Modify | `boardfarm3/api/plugin.py` — use generator in hookimpl |
| Modify | `boardfarm3/api/app.py` — add `_strip_sphinx_params`, schema wrapper, skipped-routes state, `/diagnostics/skipped-routes` endpoint |
| Modify | `unittests/api/test_routers_lan.py` — update paths, add 4 tests |
| Create | `unittests/api/test_generator.py` — 6 generator unit tests |
| No change | `unittests/control/test_openapi.py` |

---

## External Plugin Contract

A plugin (e.g., `boardfarm3-docsis`) uses the generator for its own templates:

```python
# boardfarm_docsis/api/plugin.py
from pluggy import HookimplMarker
from boardfarm3.api.routers import RouterBundle
from boardfarm3.api.routers._generator import generate_template_routers
from boardfarm_docsis.templates.docsis_wan import DocsisWAN

hookimpl_api = HookimplMarker("boardfarm_api")

@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:
    routers, skipped = generate_template_routers([DocsisWAN])
    return [RouterBundle(namespace="docsis", routers=routers, skipped=skipped)]
```

For methods the generator cannot handle (non-serialisable returns, complex signatures), the plugin author writes a manual `APIRouter` and appends it to `routers`.
