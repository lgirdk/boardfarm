"""Tests that the control plane seeds the deny-list into agent environments."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import httpx
import pytest  # noqa: TC002 -- brief-mandated import, matches its verbatim test code
import respx
from fastapi.testclient import TestClient

from boardfarm3.api.routers import DISABLED_PLUGINS_ENV
from boardfarm3_control.app import _agent_env, create_app
from boardfarm3_control.launcher import FakeLauncher

if TYPE_CHECKING:
    from boardfarm3_control.models import AgentInfo


def test_env_is_seeded_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    assert _agent_env(None) == {DISABLED_PLUGINS_ENV: "beta_api"}


def test_request_value_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    assert _agent_env({DISABLED_PLUGINS_ENV: "other"}) == {
        DISABLED_PLUGINS_ENV: "other"
    }


def test_none_when_nothing_to_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DISABLED_PLUGINS_ENV, raising=False)
    assert _agent_env(None) is None


def test_other_request_env_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    assert _agent_env({"FOO": "bar"}) == {
        "FOO": "bar",
        DISABLED_PLUGINS_ENV: "beta_api",
    }


class _RecordingLauncher(FakeLauncher):
    """FakeLauncher that records the kwargs every ``start()`` call received."""

    def __init__(self) -> None:
        super().__init__()
        self.start_calls: list[dict[str, Any]] = []

    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,
        runtime_profile: str,
        agent_env: dict[str, str] | None = None,
    ) -> AgentInfo:
        self.start_calls.append(
            {
                "session_id": session_id,
                "board_name": board_name,
                "image": image,
                "runtime_profile": runtime_profile,
                "agent_env": agent_env,
            }
        )
        return await super().start(
            session_id, board_name, image, runtime_profile, agent_env=agent_env
        )


@respx.mock
def test_create_session_hands_seeded_env_to_the_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /sessions must pass the deny-list env through to the launcher."""
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    respx.get(re.compile(r"http://localhost:\d+/health")).mock(
        return_value=httpx.Response(200, json={"state": "ready"})
    )
    respx.post(re.compile(r"http://localhost:\d+/session/config")).mock(
        return_value=httpx.Response(200, json={"state": "configured"})
    )
    respx.post(re.compile(r"http://localhost:\d+/session/boot")).mock(
        return_value=httpx.Response(
            202, json={"boot_job_id": "j-abc", "state": "booting"}
        )
    )

    launcher = _RecordingLauncher()
    app = create_app(launcher, {"prplos": "boardfarm3-agent:latest"})
    client = TestClient(app, raise_server_exceptions=True)

    resp = client.post(
        "/sessions",
        json={"board_name": "board-1", "runtime_profile": "prplos", "payload": {}},
    )

    assert resp.status_code == 202
    assert len(launcher.start_calls) == 1
    assert launcher.start_calls[0]["agent_env"] == {DISABLED_PLUGINS_ENV: "beta_api"}


_RESERVED_KEYS = [
    "BOARDFARM_BOARD_NAME",
    "BOARDFARM_SESSION_ID",
    "BOARDFARM_AGENT_PORT",
]


@pytest.mark.parametrize("key", _RESERVED_KEYS)
def test_create_session_rejects_reserved_agent_env_keys(key: str) -> None:
    """A client must not re-point its agent at another board, session or port.

    Overriding ``BOARDFARM_BOARD_NAME`` would lease one board while the agent
    drives another; nothing may be launched and the board must stay free.
    """
    launcher = _RecordingLauncher()
    app = create_app(launcher, {"prplos": "boardfarm3-agent:latest"})
    client = TestClient(app)

    resp = client.post(
        "/sessions",
        json={
            "board_name": "board-1",
            "runtime_profile": "prplos",
            "payload": {},
            "agent_env": {key: "other"},
        },
    )

    assert resp.status_code == 422
    assert launcher.start_calls == []
    assert app.state.lease.held_by("board-1") is None
