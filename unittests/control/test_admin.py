"""/admin/hosts: list, create, patch and delete lab hosts at runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3_control.app import create_app
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher import MultiHostLauncher
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.models import AgentInfo

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI


def _app(tmp_path: Path, fake_daemon: Any) -> tuple[FastAPI, MultiHostLauncher]:
    daemon = fake_daemon()
    hosts = HostRegistry.load(
        tmp_path / "hosts.json",
        seed={"lab-1": {"docker_url": "tcp://10.0.0.1:2375", "default": True}},
        host_factory=lambda name, spec: DockerHost(
            name, spec, client_factory=daemon.client_factory
        ),
    )
    launcher = MultiHostLauncher(hosts, "c-test", tmp_path / "sessions.json")
    return create_app(launcher, {"prplos": "img:1"}), launcher


def _session(host: str, session_id: str = "s-1", **update: Any) -> AgentInfo:
    return AgentInfo(
        session_id=session_id,
        board_name=f"b-{session_id}",
        runtime_profile="prplos",
        container_id="c",
        host_port=1,
        created_at=0.0,
        host=host,
        **update,
    )


def test_list_and_get_hosts(tmp_path: Path, fake_daemon: Any) -> None:
    app, launcher = _app(tmp_path, fake_daemon)
    app.state.registry.add(_session("lab-1"))
    app.state.registry.add(_session("lab-1", "s-2", state="dead"))
    app.state.registry.add(_session("lab-1", "s-3", state="dead", stop_pending=True))
    client = TestClient(app)
    [view] = client.get("/admin/hosts").json()
    assert view["name"] == "lab-1"
    assert view["spec"]["docker_url"] == "tcp://10.0.0.1:2375"
    assert view["effective_registry"] is None
    assert view["status"]["breaker"] == "up"
    assert view["status"]["sessions"] == {"live": 1, "dead": 1, "stop_pending": 1}
    assert view["status"]["conflicts"] == 0
    assert client.get("/admin/hosts/lab-1").json()["name"] == "lab-1"
    assert client.get("/admin/hosts/lab-9").status_code == 404
    launcher.hosts.close()


def test_put_creates_persists_and_probes(tmp_path: Path, fake_daemon: Any) -> None:
    app, launcher = _app(tmp_path, fake_daemon)
    resp = TestClient(app).put(
        "/admin/hosts/lab-2",
        json={"docker_url": "tcp://10.0.0.2:2375", "registry": "mirror:5000"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["probe"] is True
    assert body["effective_registry"] == "mirror:5000"
    assert "lab-2" in (tmp_path / "hosts.json").read_text()
    launcher.hosts.close()


@pytest.mark.parametrize(
    ("name", "body", "needle"),
    [
        ("Bad_Name", {"docker_url": "tcp://10.0.0.2:2375"}, "host name"),
        (
            "lab-2",
            {"docker_url": "tcp://10.0.0.2:2376", "tls": {"ca": "x"}},
            "missing required keys",
        ),
        ("lab-2", {"docker_url": "tcp://10.0.0.2:2375", "colour": "red"}, "colour"),
    ],
)
def test_put_rejects_bad_records_with_422(
    tmp_path: Path, fake_daemon: Any, name: str, body: dict[str, Any], needle: str
) -> None:
    app, launcher = _app(tmp_path, fake_daemon)
    resp = TestClient(app).put(f"/admin/hosts/{name}", json=body)
    assert resp.status_code == 422
    assert needle in resp.text
    launcher.hosts.close()


def test_patch_drain_in_use_but_not_the_endpoint(
    tmp_path: Path, fake_daemon: Any
) -> None:
    app, launcher = _app(tmp_path, fake_daemon)
    app.state.registry.add(_session("lab-1"))
    client = TestClient(app)
    drained = client.patch("/admin/hosts/lab-1", json={"drain": True})
    assert drained.status_code == 200, drained.text
    assert drained.json()["spec"]["drain"] is True
    refused = client.patch("/admin/hosts/lab-1", json={"advertise_addr": "10.9.9.9"})
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "HostInUse"
    launcher.hosts.close()


def test_patch_registry_null_means_inherit(tmp_path: Path, fake_daemon: Any) -> None:
    app, launcher = _app(tmp_path, fake_daemon)
    client = TestClient(app)
    assert (
        client.patch("/admin/hosts/lab-1", json={"registry": "mirror:5000"}).status_code
        == 200
    )
    resp = client.patch("/admin/hosts/lab-1", json={"registry": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["spec"]["registry"] is None
    launcher.hosts.close()


def test_delete_refuses_a_host_with_sessions_unless_forced(
    tmp_path: Path, fake_daemon: Any
) -> None:
    app, launcher = _app(tmp_path, fake_daemon)
    info = _session("lab-1")
    app.state.registry.add(info)
    launcher.record(info)
    app.state.lease._leases[info.board_name] = info.session_id
    client = TestClient(app)
    refused = client.delete("/admin/hosts/lab-1")
    assert refused.status_code == 409
    assert refused.json()["detail"]["sessions"] == ["s-1"]
    forced = client.delete("/admin/hosts/lab-1?force=true")
    assert forced.status_code == 200, forced.text
    assert forced.json() == {"status": "deleted", "abandoned": ["s-1"]}
    assert app.state.registry.get("s-1") is None
    assert app.state.lease.held_by(info.board_name) is None
    assert launcher.entry("s-1") is None
    assert launcher.hosts.names() == []
    launcher.hosts.close()
