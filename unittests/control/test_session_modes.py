"""Sessions in a non-interactive mode, as control sees them."""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from boardfarm3_control import app as control_app
from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.models import AgentInfo, SessionCreate, SessionResponse

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


def test_the_run_fields_say_what_they_hold() -> None:
    request = SessionCreate.model_fields["run"].description
    assert request is not None
    assert "request" in request
    for model in (AgentInfo, SessionResponse):
        summary = model.model_fields["run"].description
        assert summary is not None
        assert "summary" in summary


_HEALTH = re.compile(r"http://localhost:\d+/health")
_CONFIG = re.compile(r"http://localhost:\d+/session/config")
_BOOT = re.compile(r"http://localhost:\d+/session/boot")
_STATUS = re.compile(r"http://localhost:\d+/session$")


@respx.mock
def test_a_pytest_session_is_configured_with_its_run_and_never_booted() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    config = respx.post(_CONFIG).mock(
        return_value=httpx.Response(
            200, json={"state": "running", "run": {"state": "running"}}
        )
    )
    boot = respx.post(_BOOT).mock(return_value=httpx.Response(202, json={}))
    launcher = _RecordingLauncher()
    with TestClient(create_app(launcher, _PROFILES, modes={"pytest"})) as client:
        data = client.post("/sessions", json=_PYTEST).json()
    sent = json.loads(config.calls.last.request.content)
    assert sent["mode"] == "pytest"
    assert sent["run"] == _PYTEST["run"]
    assert "skip_boot" not in sent["options"]
    assert not boot.called
    assert launcher.kwargs[0]["mode"] == "pytest"
    assert data["state"] == "running"
    assert data["mode"] == "pytest"
    assert data["run"] == {"state": "running"}


@respx.mock
def test_an_interact_session_is_still_booted_and_passes_no_mode() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    config = respx.post(_CONFIG).mock(return_value=httpx.Response(200, json={}))
    boot = respx.post(_BOOT).mock(
        return_value=httpx.Response(202, json={"state": "booting"})
    )
    launcher = _RecordingLauncher()
    body = {"board_name": "b1", "runtime_profile": "prplos", "payload": {}}
    with TestClient(create_app(launcher, _PROFILES, modes={"pytest"})) as client:
        data = client.post("/sessions", json=body).json()
    sent = json.loads(config.calls.last.request.content)
    assert "mode" not in sent
    assert sent["options"]["skip_boot"] is True
    assert boot.called
    assert "mode" not in launcher.kwargs[0]
    assert data["mode"] == "interact"
    assert data["run"] is None


@respx.mock
def test_a_live_pytest_session_reports_its_run() -> None:
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(
        return_value=httpx.Response(200, json={"state": "running"})
    )
    respx.get(_STATUS).mock(
        return_value=httpx.Response(
            200,
            json={
                "state": "finished",
                "run": {"state": "finished", "outcome": "passed"},
            },
        )
    )
    with TestClient(create_app(FakeLauncher(), _PROFILES, modes={"pytest"})) as client:
        sid = client.post("/sessions", json=_PYTEST).json()["session_id"]
        data = client.get(f"/sessions/{sid}").json()
    assert data["state"] == "finished"
    assert data["mode"] == "pytest"
    assert data["run"] == {"state": "finished", "outcome": "passed"}


def test_a_listed_corpse_shows_its_last_run() -> None:
    app = create_app(FakeLauncher(), _PROFILES, modes={"pytest"})
    with TestClient(app) as client:
        app.state.registry.add(
            AgentInfo(
                session_id="s-1",
                board_name="b1",
                runtime_profile="prplos",
                container_id="c",
                host_port=1,
                created_at=1.0,
                mode="pytest",
            )
        )
        # A recent end time: an old one would let the reaper purge the corpse.
        app.state.registry.mark_dead(
            "s-1", ended_at=time.time(), run={"outcome": "failed"}
        )
        data = client.get("/sessions/s-1").json()
    assert data["state"] == "dead"
    assert data["mode"] == "pytest"
    assert data["run"] == {"outcome": "failed"}


@respx.mock
def test_run_env_never_leaves_the_create_request() -> None:
    canary = "s3cr3t-run-env"
    summary = {"state": "running"}
    respx.get(_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_CONFIG).mock(
        return_value=httpx.Response(200, json={"state": "running", "run": summary})
    )
    respx.get(_STATUS).mock(
        return_value=httpx.Response(200, json={"state": "running", "run": summary})
    )
    body = {**_PYTEST, "run": {"test_names": ["MVX_TST-1"], "env": {"UIM_PWD": canary}}}
    app = create_app(FakeLauncher(), _PROFILES, modes={"pytest"})
    with TestClient(app) as client:
        created = client.post("/sessions", json=body)
        sid = created.json()["session_id"]
        one = client.get(f"/sessions/{sid}")
        listing = client.get("/sessions")
        stored = app.state.registry.get(sid)
    assert created.status_code == 202
    # Only the agent's summary reaches the replies, never the request's run.
    assert created.json()["run"] == summary
    assert one.json()["run"] == summary
    assert stored is not None
    for leaked_into in (
        created.text,
        one.text,
        listing.text,
        json.dumps(stored.model_dump()),
    ):
        assert canary not in leaked_into
