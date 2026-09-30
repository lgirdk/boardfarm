"""Tests for browser (CORS) access to the control plane."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher

if TYPE_CHECKING:
    import httpx
    import pytest
    from fastapi import FastAPI

_GUI = "http://scheduler.lab:8080"


def _preflight(client: TestClient, origin: str) -> httpx.Response:
    return client.options(
        "/sessions",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_preflight_is_allowed_for_a_configured_origin() -> None:
    """A listed browser origin passes the preflight for POST /sessions."""
    app = create_app(
        FakeLauncher(),
        {"prplos": "boardfarm3-agent:latest"},
        cors_origins=[_GUI],
    )
    resp = _preflight(TestClient(app), _GUI)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _GUI


def test_preflight_is_refused_for_an_unlisted_origin() -> None:
    """Only listed origins are allowed, never every origin."""
    app = create_app(
        FakeLauncher(),
        {"prplos": "boardfarm3-agent:latest"},
        cors_origins=[_GUI],
    )
    resp = _preflight(TestClient(app), "http://elsewhere.lab:8080")
    assert "access-control-allow-origin" not in resp.headers


def test_no_cors_when_origins_are_not_configured() -> None:
    """Without configured origins the control plane stays same-origin only."""
    app = create_app(FakeLauncher(), {"prplos": "boardfarm3-agent:latest"})
    resp = _preflight(TestClient(app), _GUI)
    assert "access-control-allow-origin" not in resp.headers


def test_main_reads_cors_origins_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BOARDFARM_CORS_ORIGINS is a comma-separated, whitespace-tolerant list."""
    from boardfarm3_control import __main__ as entry

    served: dict[str, FastAPI] = {}
    monkeypatch.setattr(
        entry.uvicorn,
        "run",
        lambda app, **_: served.setdefault("app", app),
    )
    monkeypatch.setenv("BOARDFARM_LAUNCHER", "process")
    monkeypatch.setenv("BOARDFARM_PROFILES", '{"prplos": "boardfarm3-agent:latest"}')
    monkeypatch.setenv(
        "BOARDFARM_CORS_ORIGINS",
        f" http://other.lab:3000 , {_GUI} ,",
    )

    entry.main()

    client = TestClient(served["app"])
    assert _preflight(client, _GUI).headers["access-control-allow-origin"] == _GUI
    assert (
        _preflight(client, "http://other.lab:3000").headers[
            "access-control-allow-origin"
        ]
        == "http://other.lab:3000"
    )
