"""Integration tests: control plane <-> agent HTTP interaction.

Each test drives the control plane via an in-process ASGI client.
The control plane starts real boardfarm3.api subprocesses (ProcessLauncher)
and proxies requests to them over real TCP.
"""

from __future__ import annotations

import io
import tarfile

import httpx

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


async def test_diagnostics_bundle_on_a_healthy_session(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """A snapshot must work on a ready session, before anything is torn down."""
    snap = await control_client.post(f"/sessions/{session}/diagnostics/snapshot")
    assert snap.status_code == 200, snap.text
    assert snap.json()["source"] == "agent"

    bundle = await control_client.get(f"/sessions/{session}/diagnostics")
    assert bundle.status_code == 200
    assert bundle.content[:2] == b"\x1f\x8b"
    with tarfile.open(fileobj=io.BytesIO(bundle.content), mode="r:gz") as archive:
        names = archive.getnames()
    assert "manifest.json" in names
    assert "jobs.json" in names
    assert "threads.txt" in names


async def test_failed_create_retains_evidence_and_frees_the_board(
    control_client: httpx.AsyncClient,
) -> None:
    """A failed session must leave evidence and must not block its board."""
    # An inventory the agent cannot resolve makes POST /session/config fail,
    # exercising the config-rejection unwind path.
    bad = await control_client.post(
        "/sessions",
        json={
            "board_name": "integration-board",
            "runtime_profile": "local",
            "payload": {"inventory": {}, "env": {}},
            "options": {"skip_boot": True},
        },
    )
    assert bad.status_code in (400, 502, 503), bad.text
    session_id = bad.json()["detail"]["session_id"]
    assert bad.json()["detail"]["diagnostics"] == (
        f"/sessions/{session_id}/diagnostics"
    )

    listed = (await control_client.get("/sessions")).json()["sessions"]
    assert any(s["session_id"] == session_id and s["state"] == "dead" for s in listed)

    bundle = await control_client.get(f"/sessions/{session_id}/diagnostics")
    assert bundle.status_code == 200
    assert bundle.content[:2] == b"\x1f\x8b"

    # The corpse must not block the board.
    good = await control_client.post(
        "/sessions",
        json={
            "board_name": "integration-board",
            "runtime_profile": "local",
            "payload": {
                "inventory": {"integration-board": {"devices": []}},
                "env": {"environment_def": {}},
            },
            "options": {"skip_boot": True},
        },
    )
    assert good.status_code == 202, good.text
    live_id = good.json()["session_id"]

    assert (await control_client.delete(f"/sessions/{session_id}")).status_code == 200
    assert (await control_client.delete(f"/sessions/{live_id}")).status_code == 200


async def test_async_mode_round_trips_through_the_control_plane(
    control_client: httpx.AsyncClient,
) -> None:
    """?mode=async must survive the proxy and yield a pollable job.

    Session creation itself always boots the agent with ``mode=async``
    (an agent boots exactly once, from CONFIGURED state, so a second manual
    ``POST .../session/boot`` on an already-booted session 409s instead of
    demonstrating anything). The resulting ``boot_job_id`` is the async
    round trip under test: it must be pollable through the control plane's
    reverse proxy via ``GET .../jobs/{id}``.
    """
    from integrationtests.control.conftest import _MINIMAL_SESSION

    resp = await control_client.post("/sessions", json=_MINIMAL_SESSION)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    session_id = body["session_id"]
    job_id = body["boot_job_id"]
    assert job_id

    job = await control_client.get(f"/sessions/{session_id}/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["job_id"] == job_id

    assert (await control_client.delete(f"/sessions/{session_id}")).status_code == 200


async def test_sse_console_stream_survives_a_quiet_period(
    control_server: str,
) -> None:
    """The old 5 s proxy read timeout severed a quiet stream; it must not now.

    This needs the real-socket ``control_server`` fixture, not the
    in-process ``control_client``: ``httpx.ASGITransport`` cannot represent
    an unbounded stream at all (see ``control_server``'s docstring), so a
    console stream over it would simply hang forever rather than prove or
    disprove anything about the proxy's timeout handling.
    """
    from integrationtests.control.conftest import _MINIMAL_SESSION

    timeout = httpx.Timeout(10.0, read=30.0)
    async with httpx.AsyncClient(base_url=control_server, timeout=timeout) as client:
        create = await client.post("/sessions", json=_MINIMAL_SESSION)
        assert create.status_code == 202, create.text
        session_id = create.json()["session_id"]

        received: list[str] = []
        async with client.stream(
            "GET",
            f"/sessions/{session_id}/console/stream",
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                received.append(line)
                # A keepalive proves the stream outlived the old ceiling.
                if line.startswith(": keepalive") or len(received) > 200:
                    break
        assert any(line.startswith(": keepalive") for line in received)

        assert (await client.delete(f"/sessions/{session_id}")).status_code == 200
