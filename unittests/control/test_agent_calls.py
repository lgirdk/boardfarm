"""Control's own calls to an agent use timeouts sized for real boards.

httpx's default is 5 s. Configuring a session (plugins parsing inventories,
constructing devices) and releasing it (closing consoles behind any running
job) both routinely take longer, and a timeout must not masquerade as the
agent rejecting the request.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher

if TYPE_CHECKING:
    from pathlib import Path

_HEALTH = re.compile(r"http://localhost:\d+/health")
_CONFIG = re.compile(r"http://localhost:\d+/session/config")
_BOOT = re.compile(r"http://localhost:\d+/session/boot")
_SESSION = re.compile(r"http://localhost:\d+/session$")
_PROFILES = {"prplos": "boardfarm3-agent:latest"}
_BODY = {"board_name": "b1", "runtime_profile": "prplos", "payload": {}}


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))


def _read_timeout(request: httpx.Request) -> float | None:
    timeout: float | None = request.extensions["timeout"]["read"]
    return timeout


@respx.mock
def test_configure_gets_the_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_AGENT_CONFIG_TIMEOUT", "77")
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    config = respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        assert client.post("/sessions", json=_BODY).status_code == 202
    assert _read_timeout(config.calls.last.request) == 77


@respx.mock
def test_a_configure_timeout_is_reported_as_a_timeout() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(side_effect=httpx.ReadTimeout("read timed out"))
    respx.delete(_SESSION).mock(return_value=httpx.Response(200, json={}))
    respx.get(re.compile(r"http://localhost:\d+/diagnostics/bundle")).mock(
        return_value=httpx.Response(200, content=b"tar")
    )
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        response = client.post("/sessions", json=_BODY)
    assert response.status_code == 504
    assert response.json()["detail"]["error"] == "AgentConfigTimeout"


@respx.mock
def test_release_gets_the_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_AGENT_RELEASE_TIMEOUT", "88")
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    respx.get(re.compile(r"http://localhost:\d+/diagnostics/bundle")).mock(
        return_value=httpx.Response(200, content=b"tar")
    )
    release = respx.delete(_SESSION).mock(return_value=httpx.Response(200, json={}))
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        session_id = client.post("/sessions", json=_BODY).json()["session_id"]
        assert client.delete(f"/sessions/{session_id}").status_code == 200
    assert _read_timeout(release.calls.last.request) == 88
