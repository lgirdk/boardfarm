"""The reconciler: every row of spec §5.3, startup, and the lifespan wiring."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi.testclient import TestClient

from boardfarm3_control.app import create_app
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher import MultiHostLauncher, docker_host
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.models import AgentInfo
from boardfarm3_control.reconcile import Reconciler
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


def _agent(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/diagnostics/bundle":
        return httpx.Response(200, content=b"BUNDLE")
    return httpx.Response(200, json={})


class _World:
    def __init__(self, tmp_path: Path, daemons: dict[str, Any]) -> None:
        self.daemons = daemons
        seed = {
            name: {"docker_url": f"tcp://10.0.0.{index}:2375"}
            for index, name in enumerate(sorted(daemons), start=1)
        }
        self.hosts = HostRegistry.load(
            tmp_path / "hosts.json",
            seed=seed,
            host_factory=lambda name, spec: DockerHost(
                name, spec, client_factory=daemons[name].client_factory, timeout=0.2
            ),
        )
        self.launcher = MultiHostLauncher(
            self.hosts, "c-test", tmp_path / "sessions.json"
        )
        self.registry = SessionRegistry()
        self.lease = BoardLease()
        self.store = DiagnosticsStore(root=tmp_path / "store")
        self.inflight: set[str] = set()
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(_agent))
        self.reconciler = Reconciler(
            launcher=self.launcher,
            registry=self.registry,
            lease=self.lease,
            store=self.store,
            inflight=self.inflight,
            http_for=lambda _info: self.http,
        )

    async def seen(self, host: str = "lab-1") -> AgentInfo:
        [info] = await self.launcher.list_host_sessions(host)
        return info

    async def close(self) -> None:
        await self.http.aclose()
        self.hosts.close()


@pytest.fixture
async def world(tmp_path: Path, fake_daemon: Any) -> AsyncIterator[_World]:
    built = _World(tmp_path, {"lab-1": fake_daemon(images={"img:1": "sha256:a"})})
    yield built
    await built.close()


def _absent(session_id: str = "s-1", **update: Any) -> AgentInfo:
    fields: dict[str, Any] = {
        "session_id": session_id,
        "board_name": "b1",
        "runtime_profile": "prplos",
        "container_id": "gone",
        "host_port": 1,
        "created_at": 0.0,
        "host": "lab-1",
    }
    fields.update(update)
    return AgentInfo(**fields)


async def test_busy_live_refreshes_the_port(world: _World) -> None:
    world.daemons["lab-1"].add_agent(
        session_id="s-1", board_name="b1", control_id="c-test"
    )
    seen = await world.seen()
    world.registry.add(
        seen.model_copy(update={"host_port": 1111, "agent_url": "http://x:1111"})
    )
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1").host_port == seen.host_port
    assert world.registry.get("s-1").agent_url == seen.agent_url


async def test_busy_pending_finishes_the_teardown(world: _World) -> None:
    daemon = world.daemons["lab-1"]
    daemon.add_agent(session_id="s-1", board_name="b1", control_id="c-test")
    pending = (await world.seen()).model_copy(
        update={"state": "dead", "stop_pending": True, "ended_at": 5.0}
    )
    world.registry.add(pending)
    world.launcher.record(pending, retained=False)
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1") is None
    assert daemon.agents("b1") == []
    assert world.launcher.entry("s-1") is None
    assert world.store.has_bundle("s-1")


async def test_busy_pending_retained_keeps_a_stopped_corpse(world: _World) -> None:
    daemon = world.daemons["lab-1"]
    daemon.add_agent(session_id="s-1", board_name="b1", control_id="c-test")
    pending = (await world.seen()).model_copy(
        update={"state": "dead", "stop_pending": True, "ended_at": 5.0}
    )
    world.registry.add(pending)
    world.launcher.record(pending, retained=True)
    await world.reconciler.reconcile_host("lab-1")
    info = world.registry.get("s-1")
    assert (info.state, info.stop_pending, info.ended_at) == ("dead", False, 5.0)
    assert daemon.agents("b1")[0].status == "exited"


async def test_busy_unknown_is_adopted_with_the_lease(world: _World) -> None:
    world.daemons["lab-1"].add_agent(
        session_id="s-1", board_name="b1", control_id="c-test"
    )
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1").state == "live"
    assert world.lease.held_by("b1") == "s-1"
    assert world.launcher.entry("s-1") is not None


async def test_busy_known_corpse_is_adopted_as_live(world: _World) -> None:
    world.daemons["lab-1"].add_agent(
        session_id="s-1", board_name="b1", control_id="c-test"
    )
    corpse = (await world.seen()).model_copy(update={"state": "dead", "ended_at": 5.0})
    world.registry.add(corpse)
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1").state == "live"
    assert world.lease.held_by("b1") == "s-1"


async def test_adoption_conflict_is_counted_not_killed(world: _World) -> None:
    await world.lease.acquire("b1", "s-other")
    world.daemons["lab-1"].add_agent(
        session_id="s-1", board_name="b1", control_id="c-test"
    )
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1").state == "live"
    assert world.lease.held_by("b1") == "s-other"
    assert world.hosts.docker_host("lab-1").conflicts == 1
    assert world.daemons["lab-1"].agents("b1")[0].status == "running"


async def test_stopped_live_is_marked_dead_and_released(world: _World) -> None:
    container = world.daemons["lab-1"].add_agent(
        session_id="s-1", board_name="b1", control_id="c-test"
    )
    world.registry.add(await world.seen())
    await world.lease.acquire("b1", "s-1")
    container.stop()
    await world.reconciler.reconcile_host("lab-1")
    info = world.registry.get("s-1")
    assert info.state == "dead"
    assert info.ended_at is not None
    assert world.lease.held_by("b1") is None


async def test_stopped_pending_archives_and_purges(world: _World) -> None:
    daemon = world.daemons["lab-1"]
    daemon.add_agent(
        session_id="s-1", board_name="b1", control_id="c-test", status="exited"
    )
    pending = (await world.seen()).model_copy(
        update={"stop_pending": True, "ended_at": 5.0}
    )
    world.registry.add(pending)
    world.launcher.record(pending, retained=False)
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1") is None
    assert daemon.agents("b1") == []
    assert world.store.has_bundle("s-1")


async def test_stopped_unknown_is_adopted_as_a_corpse(world: _World) -> None:
    world.daemons["lab-1"].add_agent(
        session_id="s-1", board_name="b1", control_id="c-test", status="exited"
    )
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1").state == "dead"
    assert world.lease.held_by("b1") is None


async def test_absent_live_is_marked_dead_and_released(world: _World) -> None:
    world.registry.add(_absent())
    await world.lease.acquire("b1", "s-1")
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1").state == "dead"
    assert world.lease.held_by("b1") is None


async def test_absent_pending_is_dropped(world: _World) -> None:
    pending = _absent(state="dead", stop_pending=True, ended_at=5.0)
    world.registry.add(pending)
    world.launcher.record(pending)
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1") is None
    assert world.launcher.entry("s-1") is None


async def test_known_corpse_is_left_to_the_reaper(world: _World) -> None:
    world.daemons["lab-1"].add_agent(
        session_id="s-1", board_name="b1", control_id="c-test", status="exited"
    )
    corpse = await world.seen()
    world.registry.add(corpse)
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1") == corpse
    assert len(world.daemons["lab-1"].agents("b1")) == 1


async def test_inflight_sessions_are_skipped(world: _World) -> None:
    world.registry.add(_absent())
    world.inflight.add("s-1")
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1").state == "live"


async def test_down_host_is_left_alone(world: _World) -> None:
    world.registry.add(_absent())
    world.daemons["lab-1"].down = True
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1").state == "live"


async def test_startup_restores_the_index_for_an_unreachable_host(
    world: _World,
) -> None:
    live = _absent("s-live")
    pending = _absent(
        "s-pend", board_name="b2", state="dead", stop_pending=True, ended_at=5.0
    )
    world.launcher.record(live)
    world.launcher.record(pending)
    world.daemons["lab-1"].down = True
    await world.reconciler.startup()
    assert world.registry.get("s-live").state == "live"
    assert world.lease.held_by("b1") == "s-live"
    assert world.registry.get("s-pend").stop_pending is True
    assert world.lease.held_by("b2") is None


async def test_startup_with_a_hung_host_is_bounded(
    tmp_path: Path, fake_daemon: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(docker_host, "_OUTER_MARGIN", 0.05)
    hung = fake_daemon()
    hung.hang = threading.Event()
    healthy = fake_daemon()
    healthy.add_agent(session_id="s-ok", board_name="b-ok", control_id="c-test")
    built = _World(tmp_path, {"lab-1": hung, "lab-2": healthy})
    started = time.monotonic()
    await built.reconciler.startup()
    assert time.monotonic() - started < 1.5
    assert built.registry.get("s-ok").state == "live"
    hung.hang.set()
    await built.close()


def test_lifespan_runs_startup_and_the_reconcile_loop(
    tmp_path: Path, fake_daemon: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path / "store"))
    daemon = fake_daemon()
    daemon.add_agent(session_id="s-1", board_name="b1", control_id="c-test")
    hosts = HostRegistry.load(
        tmp_path / "hosts.json",
        seed={"lab-1": {"docker_url": "tcp://10.0.0.1:2375", "default": True}},
        host_factory=lambda name, spec: DockerHost(
            name, spec, client_factory=daemon.client_factory
        ),
    )
    app = create_app(
        MultiHostLauncher(hosts, "c-test", tmp_path / "sessions.json"),
        {"prplos": "img:1"},
    )
    with TestClient(app):
        assert app.state.registry.get("s-1").state == "live"
        assert app.state.lease.held_by("b1") == "s-1"
        assert not app.state.reconcile.done()
    assert app.state.reconcile.cancelled()
    hosts.close()
