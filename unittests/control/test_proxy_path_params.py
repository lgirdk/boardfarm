"""Regression tests for path-parameter substitution in proxied plugin routes.

A proxied route such as ``/sessions/{sid}/core/templates/lan/{index}/foo`` must
forward the *client-supplied* value of ``{index}`` to the agent, not the literal
template segment ``{index}``.
"""

from __future__ import annotations

import httpx
import respx
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.requests import Request  # noqa: TC002

from boardfarm3_control.openapi import register_plugin_routes


class _StatsRequest(BaseModel):
    iface: str


_plugin_router = APIRouter()


@_plugin_router.post("/core/templates/lan/{index}/get_interface_stats")
async def _stats(index: int, _body: _StatsRequest) -> dict:  # noqa: ARG001
    return {"result": {}}


class _Info:
    """Minimal session info exposing an agent URL."""

    agent_url = "http://agent.local"


class _FakeRegistry:
    """Registry stub resolving a single known session id."""

    def get(self, session_id: str) -> object | None:
        """Return info for ``s-1`` only.

        :param session_id: session identifier from the request path
        :type session_id: str
        :return: session info or None when unknown
        :rtype: object | None
        """
        return _Info() if session_id == "s-1" else None

    def touch(self, session_id: str) -> None:
        """No-op activity marker.

        :param session_id: session identifier
        :type session_id: str
        """


def _client() -> TestClient:
    """Build a control-plane app with the plugin route wrapped as a proxy.

    :return: a test client bound to the app
    :rtype: TestClient
    """
    app = FastAPI()
    register_plugin_routes(app, [_plugin_router], _FakeRegistry())  # type: ignore[arg-type]
    return TestClient(app, raise_server_exceptions=True)


@respx.mock
def test_proxy_substitutes_index_path_param_into_downstream_url() -> None:
    """The agent receives the substituted index, not the literal ``{index}``."""
    captured: dict[str, str] = {}

    def capture(request: Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"result": {}})

    respx.route(host="agent.local").mock(side_effect=capture)

    resp = _client().post(
        "/sessions/s-1/core/templates/lan/0/get_interface_stats",
        json={"iface": "eth1"},
    )

    assert resp.status_code == 200
    assert captured["path"] == "/core/templates/lan/0/get_interface_stats"
    assert "{index}" not in captured["path"]
