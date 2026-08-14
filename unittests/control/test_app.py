"""Tests for the control plane HTTP routes."""

from __future__ import annotations

import re

import httpx
import respx
from fastapi.testclient import TestClient

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher

# All tests mock agent HTTP calls so no real agent is needed.
_AGENT_HEALTH = re.compile(r"http://localhost:\d+/health")
_AGENT_CONFIG = re.compile(r"http://localhost:\d+/session/config")
_AGENT_BOOT = re.compile(r"http://localhost:\d+/session/boot")
_AGENT_SESSION = re.compile(r"http://localhost:\d+/session")
_AGENT_DELETE = re.compile(r"http://localhost:\d+/session")


def _make_client(
    launcher: FakeLauncher | None = None,
    profiles: dict[str, str] | None = None,
) -> TestClient:
    if launcher is None:
        launcher = FakeLauncher()
    if profiles is None:
        profiles = {"prplos": "boardfarm3-agent:latest"}
    app = create_app(launcher, profiles)
    return TestClient(app, raise_server_exceptions=True)


@respx.mock
def test_post_sessions_happy_path() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={"state": "ready"}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={"state": "configured"}))
    respx.post(_AGENT_BOOT).mock(
        return_value=httpx.Response(202, json={"boot_job_id": "j-abc", "state": "booting"}),
    )
    client = _make_client()
    resp = client.post(
        "/sessions",
        json={"board_name": "board-1", "runtime_profile": "prplos", "payload": {}},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["board_name"] == "board-1"
    assert data["state"] == "booting"
    assert data["boot_job_id"] == "j-abc"


def test_post_sessions_unknown_profile_returns_400() -> None:
    client = _make_client()
    resp = client.post(
        "/sessions",
        json={"board_name": "board-1", "runtime_profile": "unknown", "payload": {}},
    )
    assert resp.status_code == 400


@respx.mock
def test_post_sessions_board_conflict_returns_409() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    launcher = FakeLauncher()
    client = _make_client(launcher)
    # First session succeeds
    client.post("/sessions", json={"board_name": "board-1", "runtime_profile": "prplos", "payload": {}})
    # Second session on same board must 409
    resp = client.post(
        "/sessions",
        json={"board_name": "board-1", "runtime_profile": "prplos", "payload": {}},
    )
    assert resp.status_code == 409


@respx.mock
def test_get_sessions_empty() -> None:
    client = _make_client()
    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"] == []
    assert data["total"] == 0


@respx.mock
def test_get_sessions_returns_session_state() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={"boot_job_id": "j-1"}))
    # Fan-out health call for list
    respx.get(_AGENT_SESSION).mock(
        return_value=httpx.Response(200, json={"state": "ready", "last_activity": 1.0}),
    )
    launcher = FakeLauncher()
    client = _make_client(launcher)
    client.post("/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}})
    resp = client.get("/sessions")
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["state"] == "ready"


@respx.mock
def test_get_sessions_unreachable_agent() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    respx.get(_AGENT_SESSION).mock(side_effect=httpx.ConnectError("down"))
    launcher = FakeLauncher()
    client = _make_client(launcher)
    client.post("/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}})
    resp = client.get("/sessions")
    sessions = resp.json()["sessions"]
    assert sessions[0]["state"] == "unreachable"


@respx.mock
def test_get_sessions_limit_capped_at_100() -> None:
    client = _make_client()
    resp = client.get("/sessions?limit=999")
    # Should not 422; limit is silently capped
    assert resp.status_code == 200
    assert resp.json()["limit"] == 100


@respx.mock
def test_delete_session_happy_path() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    respx.delete(_AGENT_DELETE).mock(return_value=httpx.Response(200, json={"status": "released"}))
    launcher = FakeLauncher()
    client = _make_client(launcher)
    create_resp = client.post(
        "/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
    )
    sid = create_resp.json()["session_id"]
    resp = client.delete(f"/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "released"}
    # Session is gone
    list_resp = client.get("/sessions")
    assert list_resp.json()["total"] == 0


@respx.mock
def test_delete_session_with_unreachable_agent_still_releases() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    respx.delete(_AGENT_DELETE).mock(side_effect=httpx.ConnectError("dead"))
    launcher = FakeLauncher()
    client = _make_client(launcher)
    create_resp = client.post(
        "/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
    )
    sid = create_resp.json()["session_id"]
    resp = client.delete(f"/sessions/{sid}")
    assert resp.status_code == 200
    # Board is released — same board can be acquired again
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    resp2 = client.post(
        "/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
    )
    assert resp2.status_code == 202


@respx.mock
def test_post_sessions_boot_transport_failure_releases_resources() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(side_effect=httpx.ConnectError("dead"))
    launcher = FakeLauncher()
    client = _make_client(launcher)
    resp = client.post(
        "/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
    )
    assert resp.status_code == 503
    # Board is released — same board can be acquired again immediately
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    resp2 = client.post(
        "/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
    )
    assert resp2.status_code == 202


@respx.mock
def test_post_sessions_boot_rejected_releases_resources() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(503, json={}))
    launcher = FakeLauncher()
    client = _make_client(launcher)
    resp = client.post(
        "/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
    )
    assert resp.status_code == 502
    # Board is released — same board can be acquired again immediately
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    resp2 = client.post(
        "/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
    )
    assert resp2.status_code == 202


def test_delete_unknown_session_returns_404() -> None:
    client = _make_client()
    resp = client.delete("/sessions/s-unknown")
    assert resp.status_code == 404


def test_post_sessions_returns_session_id_format() -> None:
    """Session IDs must match the s-{8 hex chars} pattern."""
    with respx.mock:
        respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
        respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
        respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
        client = _make_client()
        resp = client.post(
            "/sessions",
            json={"board_name": "board-x", "runtime_profile": "prplos", "payload": {}},
        )
    assert resp.status_code == 202
    sid = resp.json()["session_id"]
    assert re.fullmatch(r"s-[0-9a-f]{8}", sid), f"unexpected session_id format: {sid!r}"


def test_session_create_boot_defaults_to_false() -> None:
    from boardfarm3_control.models import SessionCreate

    sc = SessionCreate(board_name="b", runtime_profile="p", payload={})
    assert sc.boot is False


def test_session_create_boot_true_accepted() -> None:
    from boardfarm3_control.models import SessionCreate

    sc = SessionCreate(board_name="b", runtime_profile="p", payload={}, boot=True)
    assert sc.boot is True
