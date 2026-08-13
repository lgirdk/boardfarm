"""Integration tests: control plane <-> agent HTTP interaction.

Each test drives the control plane via an in-process ASGI client.
The control plane starts real boardfarm3.api subprocesses (ProcessLauncher)
and proxies requests to them over real TCP.
"""

from __future__ import annotations

import httpx
import pytest

from boardfarm3_control.launcher import ProcessLauncher  # noqa: F401 (type hint)


async def test_post_sessions_creates_session(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """POST /sessions returns 202 and a valid session_id."""
    assert session.startswith("s-")
    assert len(session) == 10


async def test_proxy_health_endpoint(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """Proxy transparently forwards GET /health to the agent."""
    resp = await control_client.get(f"/sessions/{session}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session
    assert "state" in data


async def test_proxy_session_status(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """Proxy forwards GET /session and returns the agent's status dict."""
    resp = await control_client.get(f"/sessions/{session}/session")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session


async def test_list_sessions_includes_agent_state(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """GET /sessions fans out to the live agent and returns its state."""
    resp = await control_client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert session in [s["session_id"] for s in data["sessions"]]


async def test_proxy_unknown_session_returns_404(
    control_client: httpx.AsyncClient,
) -> None:
    """Proxy returns 404 for a session the registry does not know."""
    resp = await control_client.get("/sessions/s-unknown/health")
    assert resp.status_code == 404


async def test_delete_session_removes_from_registry(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """DELETE /sessions/{id} removes the session and stops proxying."""
    resp = await control_client.delete(f"/sessions/{session}")
    assert resp.status_code == 200

    # Session no longer appears in the list.
    list_resp = await control_client.get("/sessions")
    ids = [s["session_id"] for s in list_resp.json()["sessions"]]
    assert session not in ids

    # Proxy returns 404 for the deleted session.
    proxy_resp = await control_client.get(f"/sessions/{session}/health")
    assert proxy_resp.status_code == 404


async def test_board_conflict_returns_409(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """POST /sessions with the same board while one session is active returns 409."""
    from integrationtests.control.conftest import _MINIMAL_SESSION  # noqa: PLC0415

    resp = await control_client.post("/sessions", json=_MINIMAL_SESSION)
    assert resp.status_code == 409
