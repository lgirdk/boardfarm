"""Tests that plugin routes appear in the unified /openapi.json."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.openapi import load_plugin_routers


# A minimal plugin router to simulate a boardfarm plugin contribution.
class _PingRequest(BaseModel):
    host: str


class _PingResponse(BaseModel):
    success: bool


_plugin_router = APIRouter()


@_plugin_router.post(
    "/use-cases/networking/ping",
    response_model=_PingResponse,
)
async def _ping(body: _PingRequest) -> _PingResponse:  # noqa: ARG001
    return _PingResponse(success=True)


def _app_with_plugin() -> object:
    launcher = FakeLauncher()
    profiles = {"prplos": "img:latest"}
    return create_app(launcher, profiles, extra_routers=[_plugin_router])


def test_plugin_route_path_appears_in_openapi() -> None:
    app = _app_with_plugin()
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert any("use-cases/networking/ping" in path for path in paths)


def test_plugin_route_request_model_in_openapi() -> None:
    app = _app_with_plugin()
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    # _PingRequest schema must appear in components or inline
    schema_str = str(schema)
    assert "PingRequest" in schema_str or "host" in schema_str


def test_plugin_route_has_session_id_in_body_not_path() -> None:
    app = _app_with_plugin()
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    # Plugin paths must NOT carry {session_id} in the URL any more
    plugin_paths = [p for p in schema["paths"] if "ping" in p]
    assert len(plugin_paths) >= 1
    assert all("/sessions/{session_id}/" not in p for p in plugin_paths)
    # The route is served at its original path (no /sessions/ prefix)
    assert any(p.endswith("/use-cases/networking/ping") for p in plugin_paths)
    # session_id field must appear as a property of the ping route's request body schema
    ping_path = next(
        p for p in plugin_paths if p.endswith("/use-cases/networking/ping")
    )
    ping_schema = schema["paths"][ping_path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    if "$ref" in ping_schema:
        ref_name = ping_schema["$ref"].split("/")[-1]
        ping_schema = schema["components"]["schemas"][ref_name]
    assert "session_id" in ping_schema.get("properties", {})


def test_load_plugin_routers_returns_list() -> None:
    # With no boardfarm_api entrypoints registered in the test environment,
    # load_plugin_routers must return an empty list (not raise).
    routers = load_plugin_routers()
    assert isinstance(routers, list)


def test_load_plugin_routers_flattens_bundle_namespace_into_route_paths() -> None:
    """Verify namespace prefix appears in flattened route paths.

    :return: None
    :rtype: None
    """
    import pluggy
    from fastapi.routing import APIRoute

    from boardfarm3.api import hookspecs as api_hookspecs
    from boardfarm3.api.routers import RouterBundle, iter_plugin_bundles
    from boardfarm3_control.openapi import _flatten_bundle

    hookimpl_api = pluggy.HookimplMarker("boardfarm_api")
    inner = APIRouter(prefix="/templates/foo")

    @inner.post("/bar", status_code=200, response_model=None)
    async def _dummy() -> dict:
        return {}

    bundle = RouterBundle(namespace="myns", routers=[inner], skipped=[])

    class _Plugin:
        @hookimpl_api
        def boardfarm_add_api_routers(self) -> list:
            return [bundle]

    pm = pluggy.PluginManager("boardfarm_api")
    pm.add_hookspecs(api_hookspecs)
    pm.register(_Plugin(), name="myns")

    routers = [_flatten_bundle(b) for b in iter_plugin_bundles(pm)]

    assert len(routers) == 1
    flat = routers[0]
    # The flat router has no prefix; paths are stored in each route.
    route_paths = [r.path for r in flat.routes if isinstance(r, APIRoute)]
    assert any("myns" in p and "templates/foo" in p and "bar" in p for p in route_paths)


def _two_plugin_manager() -> tuple[object, object]:
    """Build a PluginManager with one healthy and one raising plugin.

    :return: (plugin manager, the bundle the healthy plugin contributes)
    :rtype: tuple[object, object]
    """
    import pluggy

    from boardfarm3.api import hookspecs as api_hookspecs
    from boardfarm3.api.routers import RouterBundle

    hookimpl_api = pluggy.HookimplMarker("boardfarm_api")
    inner = APIRouter(prefix="/templates/foo")

    @inner.post("/bar", status_code=200, response_model=None)
    async def _dummy() -> dict:
        return {}

    bundle = RouterBundle(namespace="healthy", routers=[inner], skipped=[])

    class _HealthyPlugin:
        @hookimpl_api
        def boardfarm_add_api_routers(self) -> list:
            return [bundle]

    class _BrokenPlugin:
        @hookimpl_api
        def boardfarm_add_api_routers(self) -> list:
            msg = "unable to generate pydantic-core schema"
            raise RuntimeError(msg)

    pm = pluggy.PluginManager("boardfarm_api")
    pm.add_hookspecs(api_hookspecs)
    pm.register(_BrokenPlugin(), name="broken")
    pm.register(_HealthyPlugin(), name="healthy")
    return pm, bundle


def test_broken_plugin_does_not_suppress_healthy_plugin() -> None:
    """One plugin raising must not discard every other plugin's routes.

    :return: None
    :rtype: None
    """
    from fastapi.routing import APIRoute

    from boardfarm3.api.routers import iter_plugin_bundles
    from boardfarm3_control.openapi import _flatten_bundle

    pm, _ = _two_plugin_manager()
    routers = [_flatten_bundle(b) for b in iter_plugin_bundles(pm)]

    assert len(routers) == 1
    route_paths = [r.path for r in routers[0].routes if isinstance(r, APIRoute)]
    assert any("healthy" in p and "bar" in p for p in route_paths)
