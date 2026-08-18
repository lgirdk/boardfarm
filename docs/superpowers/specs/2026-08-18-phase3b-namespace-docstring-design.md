# Phase 3b: Router Namespace Prefixing and OpenAPI Docstring Cleanup Design

## Goal

Add a `RouterBundle` abstraction so every plugin declares its namespace once and all its routers are automatically prefixed (e.g., `core/templates/lan/ping`). Simultaneously fix Sphinx `:param:`/`:return:` blocks leaking into Swagger UI descriptions via a global OpenAPI schema post-processor.

## Architecture

Two independent mechanisms land in the same phase:

1. **RouterBundle** — a thin dataclass that pairs a namespace string with a list of `APIRouter` objects. `load_plugin_routers()` wraps each bundle's routers under `/{namespace}` before handing them to `create_app()`. Individual router files remain unchanged.

2. **Schema post-processor** — a closure that wraps `app.openapi` after `FastAPI(...)` construction in `create_app()`. It strips Sphinx field-list lines (`:param`, `:type`, `:return`, `:rtype`, `:raises`) from every operation description. FastAPI caches the schema after the first call, so the post-processor runs once per process.

## Tech Stack

- Python 3.11–3.13
- FastAPI / Starlette (`APIRouter.include_router` for namespace wrapping)
- Pluggy (hookspec return type annotation update only — no runtime change)
- Pydantic (no changes)

## Global Constraints

- Python target: 3.11–3.13; `ruff target-version = "py39"` — no 3.12-only syntax.
- All four linters must pass: `ruff`, `flake8`/darglint2, `mypy --disallow-untyped-defs`, `pylint`.
- Sphinx-style docstrings on all public APIs (`:param:`, `:type:`, `:return:`, `:rtype:` blocks).
- `RouterBundle.namespace` must be a plain `str`; no validation beyond that (plugin authors own correctness).
- Individual router files (`lan.py`, future `wan.py`, etc.) must not change their own prefix — namespace is applied by `load_plugin_routers()` exclusively.
- The hookspec `boardfarm_add_api_routers()` return type changes from `list[APIRouter]` to `list[RouterBundle]`; both the hookspec annotation and the core `plugin.py` hookimpl must match.
- The post-processor must not mutate descriptions that are already clean (guard: `if desc`).
- Test paths in `unittests/api/test_routers_lan.py` must be updated to use the new `/core/templates/lan/...` prefix.
- No new files — all changes land in existing modules.
- Conventional commit messages (`feat:`, `fix:` with scope).

---

## Section 1: RouterBundle

### Dataclass

Add to `boardfarm3/api/routers/__init__.py`:

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
    """
    namespace: str
    routers: list[APIRouter] = field(default_factory=list)
```

### Updated `load_plugin_routers()`

```python
def load_plugin_routers() -> list[APIRouter]:
    try:
        import pluggy
        from boardfarm3.api import hookspecs as _api_hookspecs

        _pm = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        _pm.add_hookspecs(_api_hookspecs)
        _pm.load_setuptools_entrypoints(_ENTRYPOINT_GROUP)
        bundles: list[RouterBundle] = _pm.hook.boardfarm_add_api_routers()
        result: list[APIRouter] = []
        for bundle in bundles:
            wrapper = APIRouter(prefix=f"/{bundle.namespace}")
            for router in bundle.routers:
                wrapper.include_router(router)
            result.append(wrapper)
        return result
    except Exception:  # noqa: BLE001
        return []
```

`load_plugin_routers()` still returns `list[APIRouter]` — `app.py` is unchanged.

### Hookspec annotation update

`boardfarm3/api/hookspecs.py` — change the return type annotation only:

```python
@hookspec_api
def boardfarm_add_api_routers() -> list[RouterBundle]: ...
```

Import `RouterBundle` under `TYPE_CHECKING` to avoid circular imports.

### Plugin hookimpl update

`boardfarm3/api/plugin.py`:

```python
@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:
    from boardfarm3.api.routers import RouterBundle
    from boardfarm3.api.routers.lan import router as lan_router
    return [RouterBundle(namespace="core", routers=[lan_router])]
```

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

### Stripper function

Add to `boardfarm3/api/app.py` (module-level private):

```python
def _strip_sphinx_params(text: str) -> str:
    """Return the introductory paragraph of a Sphinx docstring.

    Strips all lines from the first Sphinx field-list marker onward
    (``:``, e.g. ``:param``, ``:type``, ``:return:``, ``:raises:``).

    :param text: raw docstring text
    :type text: str
    :return: clean introductory description
    :rtype: str
    """
    clean: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith(":"):
            break
        clean.append(line)
    return "\n".join(clean).rstrip()
```

### Schema wrapper in `create_app()`

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

FastAPI caches the schema after the first call to `app.openapi()`, so `_clean_openapi` runs exactly once per process.

---

## Section 3: Tests

### `unittests/api/test_routers_lan.py`

All 11 existing tests update their URL paths from `/templates/lan/...` to `/core/templates/lan/...`.

Three new tests added to the same file:

- `test_namespace_prefix_applied` — asserts `/core/templates/lan/ping` is in the OpenAPI schema; asserts `/templates/lan/ping` is absent.
- `test_routerbundle_wraps_multiple_routers` — creates a `RouterBundle("ns", [router_a, router_b])`, calls `load_plugin_routers()` via a patched PM, and verifies both `/ns/a/...` and `/ns/b/...` paths appear.
- `test_openapi_description_no_sphinx_params` — fetches `/openapi.json` from the test client, iterates all operation descriptions, asserts none contain `:param` or `:rtype`.

### `unittests/control/test_openapi.py`

`test_plugin_route_is_prefixed_with_session_id` already uses `all(p.startswith("/sessions/{session_id}/") ...)` — no change needed (the control plane adds that outer prefix on top of whatever the router returns).

---

## External Plugin Contract

A plugin (e.g., `boardfarm3-docsis`) that contributes routers does:

```python
# boardfarm_docsis/api/plugin.py
from pluggy import HookimplMarker
from boardfarm3.api.routers import RouterBundle

hookimpl_api = HookimplMarker("boardfarm_api")

@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:
    from boardfarm_docsis.api.routers.wan import router as wan_router
    return [RouterBundle(namespace="docsis", routers=[wan_router])]
```

Routes registered by `wan_router` (with prefix `/templates/wan`) appear at `/docsis/templates/wan/...`.
