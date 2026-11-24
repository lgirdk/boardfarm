"""Control never reaches an agent that is not the session's own.

A dead session keeps its ``agent_url``; once its container stops, Docker may
hand that host port to another session's agent. Control therefore refuses
to proxy to non-live sessions and stamps every agent call with the session
id, which the agent checks.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx
import pytest
import respx
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from boardfarm3_control import app as app_module
from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher

if TYPE_CHECKING:
    from pathlib import Path

_HEALTH = re.compile(r"http://localhost:\d+/health")
_CONFIG = re.compile(r"http://localhost:\d+/session/config")
_BOOT = re.compile(r"http://localhost:\d+/session/boot")
_HEADER = "x-boardfarm-session"
_PROFILES = {"prplos": "boardfarm3-agent:latest"}


class _EchoRequest(BaseModel):
    text: str


_plugin_router = APIRouter()


@_plugin_router.post("/core/use_cases/demo/echo")
async def _echo(body: _EchoRequest) -> dict:  # noqa: ARG001
    return {"result": "unused"}


def _create(client: TestClient, board: str = "b1") -> str:
    response = client.post(
        "/sessions",
        json={"board_name": board, "runtime_profile": "prplos", "payload": {}},
    )
    assert response.status_code == 202, response.text
    session_id: str = response.json()["session_id"]
    return session_id


@respx.mock
def test_control_stamps_its_own_agent_calls_with_the_session_id() -> None:
    health = respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    config = respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    boot = respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        session_id = _create(client)
    for route in (health, config, boot):
        assert route.calls.last.request.headers[_HEADER] == session_id


@respx.mock
def test_catch_all_proxy_stamps_the_session_id() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    echo = respx.get(re.compile(r"http://localhost:\d+/custom/echo")).mock(
        return_value=httpx.Response(200, json={"ok": True}),
    )
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        session_id = _create(client)
        assert client.get(f"/sessions/{session_id}/custom/echo").status_code == 200
    assert echo.calls.last.request.headers[_HEADER] == session_id


@respx.mock
def test_plugin_route_stamps_the_session_id() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    echo = respx.post(
        re.compile(r"http://localhost:\d+/core/use_cases/demo/echo")
    ).mock(
        return_value=httpx.Response(200, json={"result": "hi"}),
    )
    app = create_app(FakeLauncher(), _PROFILES, extra_routers=[_plugin_router])
    with TestClient(app) as client:
        session_id = _create(client)
        response = client.post(
            "/core/use_cases/demo/echo",
            json={"session_id": session_id, "text": "hi"},
        )
        assert response.status_code == 200
    assert echo.calls.last.request.headers[_HEADER] == session_id


@respx.mock
def test_dead_session_is_never_proxied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both proxy paths answer 410 for a dead session and never touch its old port."""
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    monkeypatch.setattr(app_module, "_HEALTH_TIMEOUT", 0.2)
    respx.get(_HEALTH).mock(return_value=httpx.Response(503))
    stale = respx.route(url__regex=r"http://localhost:\d+/(session|core/.*)").mock(
        return_value=httpx.Response(200, json={}),
    )
    app = create_app(FakeLauncher(), _PROFILES, extra_routers=[_plugin_router])
    with TestClient(app) as client:
        failed = client.post(
            "/sessions",
            json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}},
        )
        session_id = failed.json()["detail"]["session_id"]
        assert app.state.registry.get(session_id).state == "dead"
        stale.reset()

        catch_all = client.get(f"/sessions/{session_id}/session")
        plugin = client.post(
            "/core/use_cases/demo/echo",
            json={"session_id": session_id, "text": "hi"},
        )

    assert catch_all.status_code == 410
    assert catch_all.json()["detail"]["error"] == "SessionNotLive"
    assert plugin.status_code == 410
    assert not stale.called


# -- the agent's lifecycle belongs to control --------------------------------
#
# Reconfiguring, re-booting or releasing an agent behind control's back leaves
# the registry and the lease describing a session that no longer exists.


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "session/config"),
        ("POST", "session/boot"),
        ("DELETE", "session"),
        ("POST", "./session//config"),
        ("POST", "session/config/"),
    ],
)
@respx.mock
def test_proxy_refuses_agent_lifecycle_calls(method: str, path: str) -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        session_id = _create(client)
        lifecycle = respx.route(url__regex=r"http://localhost:\d+/session.*").mock(
            return_value=httpx.Response(200, json={}),
        )
        response = client.request(method, f"/sessions/{session_id}/{path}", json={})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "ManagedByControl"
    assert not lifecycle.called


@pytest.mark.parametrize(
    ("method", "path", "forwarded"),
    [
        ("DELETE", "session%3F", "/session%3F"),
        ("DELETE", "session%23", "/session%23"),
        ("POST", "session/config%3Fx=1", "/session/config%3Fx=1"),
    ],
)
@respx.mock
def test_encoded_query_cannot_reach_a_lifecycle_route(
    method: str, path: str, forwarded: str
) -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        session_id = _create(client)
        respx.route(url__regex=r"http://localhost:\d+/session.*").mock(
            return_value=httpx.Response(404, json={})
        )
        client.request(method, f"/sessions/{session_id}/{path}", json={})
    # Still encoded: the agent sees an unknown path, not /session or a query.
    forwarded_request = respx.calls.last.request
    assert forwarded_request.url.raw_path == forwarded.encode()
    assert not forwarded_request.url.query


@respx.mock
def test_proxy_still_serves_agent_status() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    status = respx.get(re.compile(r"http://localhost:\d+/session$")).mock(
        return_value=httpx.Response(200, json={"state": "ready"}),
    )
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        session_id = _create(client)
        response = client.get(f"/sessions/{session_id}/session")
    assert response.status_code == 200
    assert status.called


@respx.mock
def test_delete_while_a_teardown_is_running_is_409() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    launcher = FakeLauncher()
    app = create_app(launcher, _PROFILES)
    with TestClient(app) as client:
        session_id = _create(client)
        app.state.inflight.add(session_id)  # a teardown is already running
        response = client.delete(f"/sessions/{session_id}")
        assert response.status_code == 409
        assert app.state.registry.get(session_id) is not None
        assert app.state.lease.held_by("b1") == session_id
