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
async def _ping(_body: _PingRequest) -> _PingResponse:
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
    # session_id field must appear in the request body schema
    schema_str = str(schema)
    assert "session_id" in schema_str


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
    from unittest.mock import MagicMock, patch

    from fastapi.routing import APIRoute

    from boardfarm3.api.routers import RouterBundle

    inner = APIRouter(prefix="/templates/foo")

    @inner.post("/bar", status_code=200, response_model=None)
    async def _dummy() -> dict:
        return {}

    bundle = RouterBundle(namespace="myns", routers=[inner], skipped=[])

    with patch("pluggy.PluginManager") as mock_cls:
        mock_pm = MagicMock()
        mock_cls.return_value = mock_pm
        mock_pm.hook.boardfarm_add_api_routers.return_value = [[bundle]]
        routers = load_plugin_routers()

    assert len(routers) == 1
    flat = routers[0]
    # The flat router has no prefix; paths are stored in each route.
    route_paths = [r.path for r in flat.routes if isinstance(r, APIRoute)]
    assert any("myns" in p and "templates/foo" in p and "bar" in p for p in route_paths)
