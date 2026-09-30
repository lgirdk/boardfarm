"""Agent HTTP goes through the launcher's per-host client, else the shared pool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import DockerLauncher, FakeLauncher, ProcessLauncher
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.models import HostSpec

if TYPE_CHECKING:
    import pytest

    from boardfarm3_control.models import AgentInfo


class _ClientLauncher(FakeLauncher):
    """FakeLauncher whose agents are reached through one recording client."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[str, str]] = []
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self._agent))

    def _agent(self, request: httpx.Request) -> httpx.Response:
        self.seen.append((request.method, request.url.path))
        if request.url.path == "/session/boot":
            return httpx.Response(202, json={"boot_job_id": "j-1"})
        if request.url.path == "/session":
            return httpx.Response(200, json={"state": "ready", "booted": False})
        return httpx.Response(200, json={"ok": True})

    def agent_client(self, info: AgentInfo) -> httpx.AsyncClient:  # noqa: ARG002
        return self.client


class _PingBody(BaseModel):
    target: str


def _plugin_router() -> APIRouter:
    router = APIRouter()

    @router.post("/use-cases/test/ping")
    async def ping(body: _PingBody) -> dict[str, str]:
        return {"ran": body.target}  # never runs: the control plane proxies it

    return router


def test_create_list_proxy_and_plugin_routes_use_the_launchers_client() -> None:
    launcher = _ClientLauncher()
    app = create_app(launcher, {"prplos": "img"}, extra_routers=[_plugin_router()])
    client = TestClient(app)
    created = client.post(
        "/sessions",
        json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}},
    )
    assert created.status_code == 202, created.text
    session_id = created.json()["session_id"]
    assert client.get("/sessions").json()["sessions"][0]["state"] == "ready"
    assert client.get(f"/sessions/{session_id}/devices").status_code == 200
    plugin = client.post(
        "/use-cases/test/ping", json={"session_id": session_id, "target": "x"}
    )
    assert plugin.status_code == 200, plugin.text
    assert launcher.seen == [
        ("GET", "/health"),
        ("POST", "/session/config"),
        ("POST", "/session/boot"),
        ("GET", "/session"),
        ("GET", "/devices"),
        ("POST", "/use-cases/test/ping"),
    ]


def test_shared_pool_takes_its_size_from_the_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDFARM_PROXY_MAX_CONNECTIONS", "7")
    app = create_app(FakeLauncher(), {"prplos": "img"})
    with TestClient(app):
        pool = app.state.http._transport._pool
        assert pool._max_connections == 7
        assert pool._max_keepalive_connections == 7


async def test_builtin_launchers_defer_to_the_shared_pool(fake_daemon: Any) -> None:
    info = await FakeLauncher().start("s-1", "b1", "img", "prplos")
    host = DockerHost("lab-1", HostSpec(), client_factory=fake_daemon().client_factory)
    assert FakeLauncher().agent_client(info) is None
    assert ProcessLauncher().agent_client(info) is None
    assert DockerLauncher(host, "c-test").agent_client(info) is None
    host.close()
