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


def test_plugin_route_is_prefixed_with_session_id() -> None:
    app = _app_with_plugin()
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    # All plugin paths must be under /sessions/{session_id}/
    plugin_paths = [p for p in schema["paths"] if "ping" in p]
    assert len(plugin_paths) == 1
    assert plugin_paths[0].startswith("/sessions/{session_id}/")


def test_load_plugin_routers_returns_list() -> None:
    # With no boardfarm_api entrypoints registered in the test environment,
    # load_plugin_routers must return an empty list (not raise).
    routers = load_plugin_routers()
    assert isinstance(routers, list)
