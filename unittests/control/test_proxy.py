"""Tests for the streaming proxy helper."""

from __future__ import annotations

import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request  # noqa: TC002

from boardfarm3_control.proxy import _HOP_BY_HOP, proxy_request

# A minimal FastAPI app that exposes the proxy for testing.
_proxy_app = FastAPI()


@_proxy_app.get("/proxy-test/{path:path}")
async def _proxy_route(path: str, request: Request) -> object:
    return await proxy_request(request, "http://fake-agent", path)


_client = TestClient(_proxy_app, raise_server_exceptions=True)


@respx.mock
def test_proxy_forwards_json_response() -> None:
    respx.get("http://fake-agent/session").mock(
        return_value=httpx.Response(200, json={"state": "ready"}),
    )
    resp = _client.get("/proxy-test/session")
    assert resp.status_code == 200
    assert resp.json()["state"] == "ready"


@respx.mock
def test_proxy_returns_502_on_connect_error() -> None:
    respx.get("http://fake-agent/session").mock(side_effect=httpx.ConnectError("down"))
    resp = _client.get("/proxy-test/session")
    assert resp.status_code == 502


@respx.mock
def test_proxy_strips_hop_by_hop_from_response() -> None:
    respx.get("http://fake-agent/session").mock(
        return_value=httpx.Response(
            200,
            json={},
            headers={"connection": "keep-alive", "x-custom": "kept"},
        ),
    )
    resp = _client.get("/proxy-test/session")
    assert "connection" not in resp.headers
    assert resp.headers.get("x-custom") == "kept"


@respx.mock
def test_proxy_strips_hop_by_hop_from_forwarded_request() -> None:
    captured_headers: dict[str, str] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json={})

    respx.get("http://fake-agent/session").mock(side_effect=capture)
    _client.get(
        "/proxy-test/session",
        headers={"connection": "keep-alive", "upgrade": "websocket", "x-keep": "yes"},
    )
    assert "connection" not in captured_headers
    assert "upgrade" not in captured_headers
    assert captured_headers.get("x-keep") == "yes"


def test_hop_by_hop_set_contains_known_headers() -> None:
    for header in ("connection", "transfer-encoding", "te", "trailer", "upgrade"):
        assert header in _HOP_BY_HOP
