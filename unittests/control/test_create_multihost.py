"""POST /sessions with a MultiHostLauncher: placement, the host gate and launch checks."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import requests
import respx
from fastapi.testclient import TestClient

from boardfarm3_control import app as app_module
from boardfarm3_control.app import create_app
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher import FakeLauncher, MultiHostLauncher
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.models import AgentInfo

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

_SEED = {
    "lab-1": {"docker_url": "tcp://10.0.0.1:2375", "default": True},
    "lab-2": {"docker_url": "tcp://10.0.0.2:2375"},
}


def _app(
    tmp_path: Path, daemons: dict[str, Any], seed: dict[str, Any] | None = None
) -> tuple[FastAPI, MultiHostLauncher]:
    hosts = HostRegistry.load(
        tmp_path / "hosts.json",
        seed=seed or _SEED,
        host_factory=lambda name, spec: DockerHost(
            name, spec, client_factory=daemons[name].client_factory
        ),
    )
    launcher = MultiHostLauncher(hosts, "c-test", tmp_path / "sessions.json")
    return create_app(launcher, {"prplos": "img:1"}), launcher


def _daemons(fake_daemon: Any, **images: str) -> dict[str, Any]:
    present = images or {"img:1": "sha256:aaa"}
    return {name: fake_daemon(images=dict(present)) for name in _SEED}


def _body(board: str = "board-1", agent_host: object = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"devices": []}
    if agent_host is not None:
        entry["agent_host"] = agent_host
    return {
        "board_name": board,
        "runtime_profile": "prplos",
        "payload": {"inventory": {board: entry}, "env": {}},
    }


def _mock_agents(host: str = r"10\.0\.0\.\d+") -> None:
    base = rf"http://{host}:\d+"
    respx.get(re.compile(base + "/health")).mock(
        return_value=httpx.Response(200, json={})
    )
    respx.post(re.compile(base + "/session/config")).mock(
        return_value=httpx.Response(200, json={})
    )
    respx.post(re.compile(base + "/session/boot")).mock(
        return_value=httpx.Response(202, json={"boot_job_id": "j-1"})
    )


@respx.mock
def test_board_runs_on_its_agent_host(tmp_path: Path, fake_daemon: Any) -> None:
    _mock_agents()
    daemons = _daemons(fake_daemon)
    app, launcher = _app(tmp_path, daemons)
    resp = TestClient(app).post("/sessions", json=_body(agent_host="lab-2"))
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["host"] == "lab-2"
    assert data["image_id"] == "sha256:aaa"
    assert data["agent_url"].startswith("http://10.0.0.2:")
    assert daemons["lab-1"].runs == []
    assert len(daemons["lab-2"].runs) == 1
    launcher.hosts.close()


@respx.mock
def test_missing_agent_host_uses_the_default_host(
    tmp_path: Path, fake_daemon: Any
) -> None:
    _mock_agents()
    app, launcher = _app(tmp_path, _daemons(fake_daemon))
    resp = TestClient(app).post("/sessions", json=_body())
    assert resp.status_code == 202, resp.text
    assert resp.json()["host"] == "lab-1"
    launcher.hosts.close()


def test_no_agent_host_and_no_default_is_400(tmp_path: Path, fake_daemon: Any) -> None:
    seed = {"lab-1": {"docker_url": "tcp://10.0.0.1:2375"}}
    app, launcher = _app(tmp_path, {"lab-1": fake_daemon()}, seed)
    resp = TestClient(app).post("/sessions", json=_body())
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "NoHostForBoard"
    launcher.hosts.close()


@pytest.mark.parametrize("agent_host", ["lab-9", 42])
def test_unknown_or_non_string_agent_host_is_400(
    tmp_path: Path, fake_daemon: Any, agent_host: object
) -> None:
    app, launcher = _app(tmp_path, _daemons(fake_daemon))
    resp = TestClient(app).post("/sessions", json=_body(agent_host=agent_host))
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "UnknownHost"
    launcher.hosts.close()


def test_draining_host_is_503_and_starts_nothing(
    tmp_path: Path, fake_daemon: Any
) -> None:
    daemons = _daemons(fake_daemon)
    seed = {**_SEED, "lab-2": {"docker_url": "tcp://10.0.0.2:2375", "drain": True}}
    app, launcher = _app(tmp_path, daemons, seed)
    resp = TestClient(app).post("/sessions", json=_body(agent_host="lab-2"))
    assert resp.status_code == 503
    assert resp.json()["detail"] == {
        "error": "HostDraining",
        "message": "host lab-2 is draining",
        "host": "lab-2",
    }
    assert daemons["lab-2"].runs == []
    launcher.hosts.close()


def test_down_host_is_503_without_touching_it(tmp_path: Path, fake_daemon: Any) -> None:
    daemons = _daemons(fake_daemon)
    app, launcher = _app(tmp_path, daemons)
    launcher.hosts.docker_host("lab-2")._failures = 2  # breaker open
    daemons["lab-2"].fail["list"] = AssertionError("the gate must stop before Docker")
    resp = TestClient(app).post("/sessions", json=_body(agent_host="lab-2"))
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "HostUnreachable"
    launcher.hosts.close()


def test_pending_stop_blocks_the_board_on_any_host(
    tmp_path: Path, fake_daemon: Any
) -> None:
    app, launcher = _app(tmp_path, _daemons(fake_daemon))
    app.state.registry.add(
        AgentInfo(
            session_id="s-old",
            board_name="board-1",
            runtime_profile="prplos",
            container_id="c-old",
            host_port=1,
            created_at=0.0,
            state="dead",
            stop_pending=True,
            host="lab-1",
        )
    )
    resp = TestClient(app).post("/sessions", json=_body(agent_host="lab-2"))
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert (detail["error"], detail["session_id"], detail["host"]) == (
        "BoardPendingStop",
        "s-old",
        "lab-1",
    )
    launcher.hosts.close()


@respx.mock
def test_failed_start_left_running_fences_the_board_at_once(
    tmp_path: Path, fake_daemon: Any
) -> None:
    """A start whose cleanup failed blocks the board on every host straight away.

    The container may still run on lab-1, which is now down; without the
    registry entry a create on lab-2 would run the board twice.
    """
    daemons = _daemons(fake_daemon)
    daemons["lab-1"].fail["start"] = requests.exceptions.ConnectionError("reset")
    daemons["lab-1"].fail["remove"] = requests.exceptions.ConnectionError("reset")
    app, launcher = _app(tmp_path, daemons)
    _mock_agents()
    client = TestClient(app)
    first = client.post("/sessions", json=_body(agent_host="lab-1"))
    assert first.status_code == 503
    second = client.post("/sessions", json=_body(agent_host="lab-2"))
    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "BoardPendingStop"
    assert daemons["lab-2"].runs == []
    launcher.hosts.close()


@respx.mock
def test_busy_board_is_409_and_releases_the_lease(
    tmp_path: Path, fake_daemon: Any
) -> None:
    _mock_agents()
    daemons = _daemons(fake_daemon)
    foreign = daemons["lab-1"].add_agent(
        session_id="s-x", board_name="board-1", control_id="c-other"
    )
    app, launcher = _app(tmp_path, daemons)
    client = TestClient(app)
    resp = client.post("/sessions", json=_body())
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "BoardBusyOnHost"
    foreign.remove()
    retry = client.post("/sessions", json=_body())
    assert retry.status_code == 202, retry.text  # the lease was released
    launcher.hosts.close()


def test_image_pull_failure_is_503(tmp_path: Path, fake_daemon: Any) -> None:
    daemons = {name: fake_daemon() for name in _SEED}
    app, launcher = _app(tmp_path, daemons)
    resp = TestClient(app).post("/sessions", json=_body())
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert (detail["error"], detail["host"], detail["image"]) == (
        "ImagePullFailed",
        "lab-1",
        "img:1",
    )
    launcher.hosts.close()


@respx.mock
def test_unwind_detail_names_the_host(
    tmp_path: Path, fake_daemon: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path / "store"))
    monkeypatch.setattr(app_module, "_HEALTH_TIMEOUT", 0.3)
    respx.route(url__regex=r"http://10\.0\.0\.\d+:\d+/.*").mock(
        return_value=httpx.Response(500)
    )
    app, launcher = _app(tmp_path, _daemons(fake_daemon))
    with TestClient(app) as client:  # the unwind tears down through the pooled client
        resp = client.post("/sessions", json=_body())
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert (detail["error"], detail["host"]) == ("AgentUnhealthy", "lab-1")
    launcher.hosts.close()


@respx.mock
def test_start_called_without_host_for_single_host_launchers() -> None:
    class _OldStart(FakeLauncher):
        async def start(  # type: ignore[override]
            self,
            session_id: str,
            board_name: str,
            image: str,
            runtime_profile: str,
            agent_env: dict[str, str] | None = None,
        ) -> AgentInfo:
            return await super().start(
                session_id, board_name, image, runtime_profile, agent_env=agent_env
            )

    _mock_agents(host="localhost")
    app = create_app(_OldStart(), {"prplos": "img"})
    resp = TestClient(app).post(
        "/sessions",
        json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["host"] is None
