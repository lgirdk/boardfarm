"""Sessions in a non-interactive mode, as control sees them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3_control import app as control_app
from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.models import AgentInfo, SessionResponse

if TYPE_CHECKING:
    from pathlib import Path

_PROFILES = {"prplos": "boardfarm3-agent:latest"}
_PYTEST: dict[str, Any] = {
    "board_name": "b1",
    "runtime_profile": "prplos",
    "payload": {},
    "mode": "pytest",
    "run": {"test_names": ["MVX_TST-1"]},
}
_SECRETS = ("s3cr3t-value-XYZ", "u;s3cr3t-ldap")
_WITH_SECRETS: dict[str, Any] = {
    **_PYTEST,
    "run": {"test_names": ["MVX_TST-1"], "env": {"UIM_PWD": _SECRETS[0]}},
    "options": {"plugin_args": {"ldap_credentials": _SECRETS[1]}},
}


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    monkeypatch.delenv("BOARDFARM_REQUIRE_MATCHING_VERSIONS", raising=False)


class _RecordingLauncher(FakeLauncher):
    def __init__(self) -> None:
        super().__init__()
        self.started: list[str] = []
        self.kwargs: list[dict[str, object]] = []

    async def start(  # type: ignore[override]
        self, session_id: str, *args: object, **kwargs: object
    ) -> AgentInfo:
        self.started.append(session_id)
        self.kwargs.append(kwargs)
        return await super().start(session_id, *args, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"mode": "interact", "run": {}}, "run is only valid"),
        ({"run": None}, "needs a run"),
        ({"boot": True}, "boot does not apply"),
    ],
)
def test_create_checks_that_mode_run_and_boot_fit(
    change: dict[str, Any], message: str
) -> None:
    with TestClient(create_app(FakeLauncher(), _PROFILES, modes={"pytest"})) as client:
        response = client.post("/sessions", json={**_PYTEST, **change})
    assert response.status_code == 422
    assert message in response.text


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({**_WITH_SECRETS, "boot": True}, id="boot-with-a-mode"),
        pytest.param({**_WITH_SECRETS, "mode": "interact"}, id="run-in-interact"),
        pytest.param(
            {k: v for k, v in _WITH_SECRETS.items() if k != "board_name"},
            id="no-board-name",
        ),
    ],
)
def test_validation_errors_never_echo_the_request(body: dict[str, Any]) -> None:
    with TestClient(create_app(FakeLauncher(), _PROFILES, modes={"pytest"})) as client:
        response = client.post("/sessions", json=body)
    assert response.status_code == 422
    for secret in _SECRETS:
        assert secret not in response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail
    assert all(isinstance(e, dict) and {"loc", "msg"} <= e.keys() for e in detail)


def test_an_unknown_mode_is_refused_before_launch() -> None:
    launcher = _RecordingLauncher()
    with TestClient(create_app(launcher, _PROFILES, modes={"pytest"})) as client:
        response = client.post("/sessions", json={**_PYTEST, "mode": "robot"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "UnknownMode"
    assert detail["modes"] == ["interact", "pytest"]
    assert launcher.started == []


def test_healthz_lists_the_modes() -> None:
    with TestClient(create_app(FakeLauncher(), _PROFILES, modes={"pytest"})) as client:
        assert client.get("/healthz").json()["modes"] == ["interact", "pytest"]


def test_modes_are_discovered_from_the_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control_app, "load_plugin_modes", lambda: {"robot": object})
    with TestClient(create_app(FakeLauncher(), _PROFILES)) as client:
        assert client.get("/healthz").json()["modes"] == ["interact", "robot"]


def test_records_default_to_interact() -> None:
    info = AgentInfo(
        session_id="s-1",
        board_name="b1",
        runtime_profile="prplos",
        container_id="c",
        host_port=1,
        created_at=1.0,
    )
    response = SessionResponse(
        session_id="s-1",
        board_name="b1",
        runtime_profile="prplos",
        state="ready",
        created_at=1.0,
    )
    assert (info.mode, info.run) == ("interact", None)
    assert (response.mode, response.run) == ("interact", None)
