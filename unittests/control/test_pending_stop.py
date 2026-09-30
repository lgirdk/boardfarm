"""Pending stops: DELETE on an unreachable host, the reaper, and snapshots."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

import httpx
import respx
from fastapi.testclient import TestClient

from boardfarm3_control import teardown
from boardfarm3_control.app import create_app
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher import FakeLauncher, MultiHostLauncher
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.reaper import reap_once
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore
from boardfarm3_control.teardown import teardown_session

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_AGENT = re.compile(r"http://10\.0\.0\.1:\d+/.*")


def _launcher(tmp_path: Path, daemon: Any) -> MultiHostLauncher:
    hosts = HostRegistry.load(
        tmp_path / "hosts.json",
        seed={"lab-1": {"docker_url": "tcp://10.0.0.1:2375", "default": True}},
        host_factory=lambda name, spec: DockerHost(
            name, spec, client_factory=daemon.client_factory
        ),
    )
    return MultiHostLauncher(hosts, "c-test", tmp_path / "sessions.json")


def test_bundle_read_timeout_is_bounded() -> None:
    assert teardown._BUNDLE_TIMEOUT.read == 30.0


async def test_teardown_on_an_unreachable_host_leaves_a_pending_stop(
    tmp_path: Path, fake_daemon: Any
) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    launcher = _launcher(tmp_path, daemon)
    info = await launcher.start("s-1", "board-1", "img:1", "prplos", host="lab-1")
    registry = SessionRegistry()
    registry.add(info)
    lease = BoardLease()
    await lease.acquire("board-1", "s-1")
    daemon.down = True
    agent = httpx.MockTransport(lambda _request: httpx.Response(503))
    async with httpx.AsyncClient(transport=agent) as http:
        status = await teardown_session(
            session_id="s-1",
            info=info,
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=DiagnosticsStore(root=tmp_path / "store"),
            http=http,
            retain=False,
        )
    assert status == "stop_pending"
    entry = registry.get("s-1")
    assert entry.state == "dead"
    assert entry.stop_pending is True
    assert lease.held_by("board-1") is None
    assert launcher.entry("s-1").info.stop_pending is True
    launcher.hosts.close()


async def test_single_host_stop_failure_is_not_pending(tmp_path: Path) -> None:
    class _StopFails(FakeLauncher):
        async def stop(self, session_id: str, *, remove: bool = True) -> None:  # noqa: ARG002
            msg = "boom"
            raise RuntimeError(msg)

    launcher = _StopFails()
    info = await launcher.start("s-1", "board-1", "img", "prplos")
    registry = SessionRegistry()
    registry.add(info)
    agent = httpx.MockTransport(lambda _request: httpx.Response(503))
    async with httpx.AsyncClient(transport=agent) as http:
        status = await teardown_session(
            session_id="s-1",
            info=info,
            launcher=launcher,
            registry=registry,
            lease=BoardLease(),
            store=DiagnosticsStore(root=tmp_path),
            http=http,
            retain=False,
        )
    assert status == "released"
    assert registry.get("s-1").state == "dead"
    assert registry.get("s-1").stop_pending is False


@respx.mock
def test_delete_returns_202_then_503_then_purges(
    tmp_path: Path, fake_daemon: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path / "store"))
    respx.route(url__regex=_AGENT).mock(return_value=httpx.Response(503))
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    launcher = _launcher(tmp_path, daemon)
    info = asyncio.run(
        launcher.start("s-1", "board-1", "img:1", "prplos", host="lab-1")
    )
    app = create_app(launcher, {"prplos": "img:1"})
    with TestClient(app) as client:
        app.state.registry.add(info)
        app.state.lease._leases["board-1"] = "s-1"
        daemon.down = True
        first = client.delete("/sessions/s-1")
        assert first.status_code == 202, first.text
        assert first.json() == {"status": "stop_pending"}
        assert app.state.lease.held_by("board-1") is None
        again = client.delete("/sessions/s-1")
        assert again.status_code == 503
        assert again.json()["detail"]["error"] == "HostUnreachable"
        assert app.state.registry.get("s-1").stop_pending is True
        daemon.down = False
        launcher.hosts.docker_host("lab-1")._failures = 0  # as a reconciler ping would
        done = client.delete("/sessions/s-1")
        assert done.json() == {"status": "purged"}
        assert daemon.agents() == []
        assert launcher.entry("s-1") is None
    launcher.hosts.close()


@respx.mock
def test_snapshot_does_not_clear_stop_pending(
    tmp_path: Path, fake_daemon: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path / "store"))
    respx.route(url__regex=_AGENT).mock(
        return_value=httpx.Response(200, content=b"BUNDLE")
    )
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    launcher = _launcher(tmp_path, daemon)
    info = asyncio.run(
        launcher.start("s-1", "board-1", "img:1", "prplos", host="lab-1")
    )
    app = create_app(launcher, {"prplos": "img:1"})
    with TestClient(app) as client:
        app.state.registry.add(info)
        daemon.down = True  # the daemon is hung; the agent still answers
        assert client.delete("/sessions/s-1").status_code == 202
        snap = client.post("/sessions/s-1/diagnostics/snapshot")
        assert snap.status_code == 200, snap.text
        assert app.state.registry.get("s-1").stop_pending is True
        assert launcher.entry("s-1").info.stop_pending is True
    launcher.hosts.close()


def test_delete_on_a_dead_session_releases_its_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    launcher = FakeLauncher()
    info = asyncio.run(launcher.start("s-1", "board-1", "img", "prplos"))
    app = create_app(launcher, {"prplos": "img"})
    app.state.registry.add(info.model_copy(update={"state": "dead", "ended_at": 1.0}))
    app.state.lease._leases["board-1"] = "s-1"
    resp = TestClient(app).delete("/sessions/s-1")
    assert resp.json() == {"status": "purged"}
    assert app.state.lease.held_by("board-1") is None


async def test_reaper_skips_pending_stop_and_survives_purge_failure(
    tmp_path: Path,
) -> None:
    class _FlakyPurge(FakeLauncher):
        async def purge(self, session_id: str) -> None:
            if session_id == "s-bad":
                msg = "daemon hiccup"
                raise RuntimeError(msg)
            await super().purge(session_id)

    launcher = _FlakyPurge()
    registry = SessionRegistry()
    for session_id, pending in (("s-pending", True), ("s-bad", False), ("s-ok", False)):
        info = await launcher.start(session_id, f"b-{session_id}", "img", "prplos")
        registry.add(
            info.model_copy(
                update={"state": "dead", "ended_at": 1.0, "stop_pending": pending}
            )
        )
    counts = await reap_once(
        launcher=launcher,
        registry=registry,
        store=DiagnosticsStore(root=tmp_path),
        now=10**9,
    )
    assert counts["containers"] == 1
    assert registry.get("s-pending") is not None
    assert registry.get("s-bad") is not None
    assert registry.get("s-ok") is None
