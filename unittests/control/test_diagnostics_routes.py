"""Three-tier resolution of the control plane diagnostics endpoint."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.store import DiagnosticsStore

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_NOT_FOUND = 404


@pytest.fixture(name="wired")
def wired_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profiles: dict[str, str],
) -> tuple:
    """Return an app with one registered session and a temp store.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    :param profiles: profile map
    :type profiles: dict[str, str]
    :return: (app, launcher, store, agent_url)
    :rtype: tuple
    """
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    launcher = FakeLauncher()
    info = asyncio.run(launcher.start("s-1", "board", "img", "prplos"))
    app = create_app(launcher=launcher, profiles=profiles)
    return app, launcher, DiagnosticsStore(root=tmp_path), info.agent_url


@respx.mock
def test_tier1_streams_from_a_live_agent(wired: tuple) -> None:
    app, _, _, agent_url = wired
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(
            200,
            content=b"LIVE",
            headers={"content-type": "application/gzip"},
        ),
    )
    with TestClient(app) as client:
        response = client.get("/sessions/s-1/diagnostics")
    assert response.status_code == HTTP_OK
    assert response.content == b"LIVE"


@respx.mock
def test_tier2_serves_the_archived_bundle(wired: tuple) -> None:
    app, _, store, agent_url = wired
    store.write_bundle("s-1", [b"ARCHIVED"])
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    with TestClient(app) as client:
        response = client.get("/sessions/s-1/diagnostics")
    assert response.status_code == HTTP_OK
    assert response.content == b"ARCHIVED"


@respx.mock
def test_tier3_builds_from_the_launcher(wired: tuple) -> None:
    app, _, _, agent_url = wired
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    with TestClient(app) as client:
        response = client.get("/sessions/s-1/diagnostics")
    assert response.status_code == HTTP_OK
    assert response.content


def test_unknown_session_is_404(wired: tuple) -> None:
    app, _, _, _ = wired
    with TestClient(app) as client:
        assert client.get("/sessions/nope/diagnostics").status_code == HTTP_NOT_FOUND


@respx.mock
def test_snapshot_reports_its_source(wired: tuple) -> None:
    app, _, store, agent_url = wired
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"SNAP"),
    )
    with TestClient(app) as client:
        body = client.post("/sessions/s-1/diagnostics/snapshot").json()
    assert body["source"] == "agent"
    assert body["size"] == len(b"SNAP")
    assert store.bundle_path("s-1").read_bytes() == b"SNAP"


def test_unknown_session_snapshot_is_404(wired: tuple) -> None:
    app, _, _, _ = wired
    with TestClient(app) as client:
        response = client.post("/sessions/nope/diagnostics/snapshot")
    assert response.status_code == HTTP_NOT_FOUND


@respx.mock
def test_diagnostics_route_is_not_swallowed_by_the_catch_all(wired: tuple) -> None:
    """Prove /diagnostics is matched by the dedicated route, not the proxy.

    The catch-all proxy forwards to ``{agent_url}/{path}`` and turns a
    connect failure into a 502. If /diagnostics were falling through to the
    catch-all, an unreachable agent with no archive and no launcher capture
    would surface as a 502, not the three-tier 404 this route produces.
    """
    app, launcher, _, agent_url = wired
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    with TestClient(app) as client:
        # Registry now knows "s-1" (populated from the launcher at startup).
        # Drop it from the launcher too, so tier 3's capture_logs/capture_files
        # come back empty and every tier is exhausted.
        launcher._sessions.clear()
        response = client.get("/sessions/s-1/diagnostics")
    assert response.status_code == HTTP_NOT_FOUND
    assert response.json()["detail"]["error"] == "NoDiagnostics"


@respx.mock
def test_snapshot_route_is_not_swallowed_by_the_catch_all(wired: tuple) -> None:
    """Prove /diagnostics/snapshot is a real route, not a proxied sub-path.

    The catch-all would treat "diagnostics/snapshot" as the proxied path and
    forward a POST to ``{agent_url}/diagnostics/snapshot``, which the fake
    agent doesn't serve. The dedicated route instead forces a capture and
    returns the {path, size, source, captured_at} shape.
    """
    app, _, _, agent_url = wired
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"SNAP2"),
    )
    with TestClient(app) as client:
        response = client.post("/sessions/s-1/diagnostics/snapshot")
    assert response.status_code == HTTP_OK
    body = response.json()
    assert set(body) == {"path", "size", "source", "captured_at"}
