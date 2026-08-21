"""Tests for per-bundle error shaping at the control-plane dispatch edge."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from boardfarm3.api.routers import RouterBundle
from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.openapi import _flatten_bundle

HTTP_OK = 200
HTTP_NOT_FOUND = 404


class _PokeRequest(BaseModel):
    """Body model for the fake plugin route."""

    label: str


def _shaper(exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=HTTP_OK, content={"shaped": type(exc).__name__})


def _plugin_router() -> APIRouter:
    router = APIRouter()

    @router.post("/poke")
    async def _poke(body: _PokeRequest) -> dict[str, str]:  # noqa: ARG001
        return {"ok": "yes"}

    return router


def _stamped_router() -> APIRouter:
    bundle = RouterBundle(
        namespace="probe",
        routers=[_plugin_router()],
        error_shaper=_shaper,
        optional_session_id=True,
    )
    return _flatten_bundle(bundle)


def _client(router: APIRouter) -> TestClient:
    app = create_app(FakeLauncher(), {"prplos": "img:latest"}, extra_routers=[router])
    return TestClient(app)


def test_flatten_bundle_stamps_the_shaper_on_endpoints() -> None:
    flat = _stamped_router()
    route = flat.routes[0]
    assert getattr(route.endpoint, "__bf_error_shaper__", None) is _shaper  # type: ignore[attr-defined]
    assert getattr(route.endpoint, "__bf_optional_session_id__", False) is True  # type: ignore[attr-defined]


def test_flatten_bundle_leaves_plain_bundles_unstamped() -> None:
    flat = _flatten_bundle(RouterBundle(namespace="probe", routers=[_plugin_router()]))
    route = flat.routes[0]
    assert getattr(route.endpoint, "__bf_error_shaper__", None) is None  # type: ignore[attr-defined]


def test_unknown_session_is_shaped_to_200() -> None:
    with _client(_stamped_router()) as client:
        resp = client.post(
            "/probe/poke",
            json={"session_id": "nope", "label": "x"},
        )
    assert resp.status_code == HTTP_OK
    assert resp.json()["shaped"] == "HTTPException"


def test_missing_session_id_is_shaped_to_200() -> None:
    with _client(_stamped_router()) as client:
        resp = client.post("/probe/poke", json={"label": "x"})
    assert resp.status_code == HTTP_OK
    assert resp.json()["shaped"] == "HTTPException"


def test_unstamped_bundle_still_returns_native_404() -> None:
    plain = _flatten_bundle(
        RouterBundle(namespace="probe", routers=[_plugin_router()]),
    )
    with _client(plain) as client:
        resp = client.post(
            "/probe/poke",
            json={"session_id": "nope", "label": "x"},
        )
    assert resp.status_code == HTTP_NOT_FOUND
