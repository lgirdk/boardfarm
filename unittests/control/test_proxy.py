"""Tests for the streaming proxy helper."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request  # noqa: TC002

from boardfarm3_control.proxy import _HOP_BY_HOP, is_streaming_path, proxy_request

# A minimal FastAPI app that exposes the proxy for testing.
_proxy_app = FastAPI()


@_proxy_app.get("/proxy-test/{path:path}")
async def _proxy_route(path: str, request: Request) -> object:
    return await proxy_request(request, "http://fake-agent", path)


_client = TestClient(_proxy_app, raise_server_exceptions=True)


@_proxy_app.post("/override-test/{path:path}")
async def _override_route(path: str, request: Request) -> object:
    return await proxy_request(request, "http://fake-agent", path, body=b'{"x": 1}')


@_proxy_app.post("/cl-test/{path:path}")
async def _cl_route(path: str, request: Request) -> object:
    return await proxy_request(request, "http://fake-agent", path, body=b'{"x": 1}')


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


@respx.mock
def test_proxy_uses_body_override_instead_of_request_body() -> None:
    """When body override is provided it is forwarded instead of the original."""
    captured: dict[str, bytes] = {}

    def capture(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content
        return httpx.Response(200, json={})

    respx.post("http://fake-agent/action").mock(side_effect=capture)

    resp = _client.post("/override-test/action", json={"original": "ignored"})
    assert resp.status_code == 200
    assert captured["body"] == b'{"x": 1}'


@respx.mock
def test_proxy_body_override_sets_correct_content_length() -> None:
    """content-length forwarded to the agent must match the override body."""
    captured_headers: dict[str, str] = {}

    def capture(req: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(req.headers))
        return httpx.Response(200, json={})

    respx.post("http://fake-agent/action").mock(side_effect=capture)

    _client.post("/cl-test/action", json={"original": "longer payload here"})
    # The override body is b'{"x": 1}' (8 bytes); httpx computes content-length
    # from it, not from the larger original request body.
    assert captured_headers.get("content-length") == str(len(b'{"x": 1}'))


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("console/stream", True),
        ("/console/stream/", True),
        ("diagnostics", True),
        ("diagnostics/bundle", True),
        ("session", False),
        ("jobs/j-1a2b", False),
        ("use-cases/networking/ping", False),
    ],
)
def test_is_streaming_path(path: str, expected: bool) -> None:
    assert is_streaming_path(path) is expected


@respx.mock
def test_streaming_path_gets_unbounded_read_timeout() -> None:
    captured: dict[str, object] = {}

    def capture(req: httpx.Request) -> httpx.Response:
        captured["timeout"] = req.extensions.get("timeout")
        return httpx.Response(200, text="data: hi\n\n")

    respx.get("http://fake-agent/console/stream").mock(side_effect=capture)
    _client.get("/proxy-test/console/stream")
    assert captured["timeout"]["read"] is None


@respx.mock
def test_non_streaming_path_gets_long_read_timeout() -> None:
    captured: dict[str, object] = {}

    def capture(req: httpx.Request) -> httpx.Response:
        captured["timeout"] = req.extensions.get("timeout")
        return httpx.Response(200, json={})

    respx.get("http://fake-agent/session").mock(side_effect=capture)
    _client.get("/proxy-test/session")
    assert captured["timeout"]["read"] == 1800.0
