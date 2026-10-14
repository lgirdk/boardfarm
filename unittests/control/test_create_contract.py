"""What control reports about a session, and when it refuses to start one."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from boardfarm3.api.entrypoints import plugin_versions
from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher

if TYPE_CHECKING:
    from pathlib import Path

    from boardfarm3_control.models import AgentInfo

_HEALTH = re.compile(r"http://localhost:\d+/health")
_CONFIG = re.compile(r"http://localhost:\d+/session/config")
_BOOT = re.compile(r"http://localhost:\d+/session/boot")
_STATUS = re.compile(r"http://localhost:\d+/session$")
_BUNDLE = re.compile(r"http://localhost:\d+/diagnostics/bundle")
_PROFILES = {"prplos": "boardfarm3-agent:latest"}
_BODY = {"board_name": "b1", "runtime_profile": "prplos", "payload": {}}


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    monkeypatch.delenv("BOARDFARM_REQUIRE_MATCHING_VERSIONS", raising=False)


class _RecordingLauncher(FakeLauncher):
    def __init__(self) -> None:
        super().__init__()
        self.started: list[str] = []

    async def start(  # type: ignore[override]
        self, session_id: str, *args: object, **kwargs: object
    ) -> AgentInfo:
        self.started.append(session_id)
        return await super().start(session_id, *args, **kwargs)  # type: ignore[arg-type]


def _mock_agent(health: dict | None = None) -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json=health or {}))
    respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_BOOT).mock(
        return_value=httpx.Response(
            202, json={"state": "booting", "boot_job_id": "j-1"}
        )
    )


@respx.mock
def test_create_reports_the_state_the_agent_is_in() -> None:
    """boot=false still runs a connect job: the session is not ready yet."""
    _mock_agent()
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        data = client.post("/sessions", json=_BODY).json()
    assert data["state"] == "booting"
    assert data["boot_job_id"] == "j-1"


@respx.mock
def test_board_missing_from_the_inventory_is_refused_before_launch() -> None:
    launcher = _RecordingLauncher()
    app = create_app(launcher, _PROFILES)
    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json={
                "board_name": "b1",
                "runtime_profile": "prplos",
                "payload": {"inventory": {"b2": {}}, "env": {}},
            },
        )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "BoardNotInInventory"
    assert launcher.started == []
    assert app.state.lease.held_by("b1") is None


@respx.mock
def test_a_broken_agent_reply_does_not_break_the_list() -> None:
    _mock_agent()
    respx.get(_STATUS).mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        session_id = client.post("/sessions", json=_BODY).json()["session_id"]
        response = client.get("/sessions")
    assert response.status_code == 200
    [listed] = response.json()["sessions"]
    assert listed["session_id"] == session_id
    assert listed["state"] == "unknown"


@respx.mock
def test_one_session_can_be_read_on_its_own() -> None:
    _mock_agent()
    respx.get(_STATUS).mock(
        return_value=httpx.Response(200, json={"state": "ready", "booted": True})
    )
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        session_id = client.post("/sessions", json=_BODY).json()["session_id"]
        found = client.get(f"/sessions/{session_id}")
        missing = client.get("/sessions/s-nope")
    assert found.status_code == 200
    assert found.json()["session_id"] == session_id
    assert found.json()["state"] == "ready"
    assert missing.status_code == 404


def test_control_answers_its_own_health_check() -> None:
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "boardfarm3" in response.json()["versions"]


# -- control and agent must run the same code -----------------------------------
#
# Control builds the unified OpenAPI from its own plugin set. An agent image
# with different plugins answers some of those routes with 404 -- the stale
# ``:latest`` registry images of 2026-10 did exactly that.


@respx.mock
def test_a_mismatched_agent_image_is_reported() -> None:
    agent = {**plugin_versions(), "boardfarm3": "0.0.1"}
    _mock_agent(health={"state": "created", "versions": agent})
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        data = client.post("/sessions", json=_BODY).json()
    assert data["state"] == "booting"
    assert any("boardfarm3" in warning for warning in data["warnings"])


@respx.mock
def test_a_matching_agent_image_has_no_warnings() -> None:
    _mock_agent(health={"state": "created", "versions": plugin_versions()})
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        data = client.post("/sessions", json=_BODY).json()
    assert data["warnings"] == []


@respx.mock
def test_strict_mode_refuses_a_mismatched_agent_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDFARM_REQUIRE_MATCHING_VERSIONS", "1")
    agent = {**plugin_versions(), "boardfarm3": "0.0.1"}
    _mock_agent(health={"state": "created", "versions": agent})
    respx.get(_BUNDLE).mock(return_value=httpx.Response(200, content=b"tar"))
    respx.delete(_STATUS).mock(return_value=httpx.Response(200, json={}))
    app = create_app(FakeLauncher(), _PROFILES)
    with TestClient(app) as client:
        response = client.post("/sessions", json=_BODY)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "AgentVersionMismatch"
    assert app.state.lease.held_by("b1") is None
