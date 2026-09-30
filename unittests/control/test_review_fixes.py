"""Regression tests for the whole-branch review's Important findings 1-7."""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from typing import TYPE_CHECKING, Any

import docker.errors
import httpx
import pytest
import requests
from fastapi.testclient import TestClient

from boardfarm3_control.app import create_app
from boardfarm3_control.errors import BoardBusyOnHost, HostUnreachable, StopPending
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher import FakeLauncher, MultiHostLauncher, docker_host
from boardfarm3_control.launcher.docker import DockerLauncher
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.models import AgentInfo, HostSpec
from boardfarm3_control.reconcile import Reconciler
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

CONTROL = "c-test"


def _agent(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/diagnostics/bundle":
        return httpx.Response(200, content=b"BUNDLE")
    return httpx.Response(200, json={})


def _host(daemon: Any, **kwargs: Any) -> DockerHost:
    return DockerHost(
        "lab-1",
        HostSpec(docker_url="tcp://10.0.0.1:2375"),
        client_factory=daemon.client_factory,
        **kwargs,
    )


class _World:
    def __init__(self, tmp_path: Path, daemon: Any) -> None:
        self.daemon = daemon
        self.hosts = HostRegistry.load(
            tmp_path / "hosts.json",
            seed={"lab-1": {"docker_url": "tcp://10.0.0.1:2375", "default": True}},
            host_factory=lambda name, spec: DockerHost(
                name, spec, client_factory=daemon.client_factory, timeout=0.5
            ),
        )
        self.launcher = MultiHostLauncher(
            self.hosts, CONTROL, tmp_path / "sessions.json"
        )
        self.registry = SessionRegistry()
        self.lease = BoardLease()
        self.store = DiagnosticsStore(root=tmp_path / "store")
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(_agent))
        self.reconciler = Reconciler(
            launcher=self.launcher,
            registry=self.registry,
            lease=self.lease,
            store=self.store,
            inflight=set(),
            http_for=lambda _info: self.http,
        )


@pytest.fixture
async def world(tmp_path: Path, fake_daemon: Any) -> AsyncIterator[_World]:
    built = _World(tmp_path, fake_daemon(images={"img:1": "sha256:a"}))
    yield built
    await built.http.aclose()
    built.hosts.close()


# Important 1: one failing session must not stop its host's reconcile pass.


async def test_one_failing_session_does_not_stop_the_host_pass(world: _World) -> None:
    daemon = world.daemon
    daemon.add_agent(
        session_id="s-a", board_name="b-a", control_id=CONTROL, status="exited"
    )
    daemon.add_agent(
        session_id="s-b", board_name="b-b", control_id=CONTROL, status="exited"
    )
    seen = {i.session_id: i for i in await world.launcher.list_host_sessions("lab-1")}
    pending = seen["s-a"].model_copy(update={"stop_pending": True, "ended_at": 5.0})
    world.registry.add(pending)
    world.launcher.record(pending)
    world.registry.add(
        seen["s-b"].model_copy(update={"state": "live", "ended_at": None})
    )
    await world.lease.acquire("b-b", "s-b")
    daemon.fail["remove"] = docker.errors.APIError("500 device or resource busy")
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-b").state == "dead"
    assert world.lease.held_by("b-b") is None
    assert world.registry.get("s-a").stop_pending is True  # retried next pass


async def test_capture_logs_returns_empty_on_a_daemon_error(fake_daemon: Any) -> None:
    daemon = fake_daemon()
    daemon.add_agent(session_id="s-1", board_name="b1", control_id=CONTROL)
    daemon.fail["logs"] = docker.errors.APIError("500")
    assert await DockerLauncher(_host(daemon), CONTROL).capture_logs("s-1") == b""


# Important 2: pulls must neither starve the host's pool nor run once per create.


async def test_concurrent_creates_share_one_pull(fake_daemon: Any) -> None:
    daemon = fake_daemon(pullable={"img:1": "sha256:p"})
    daemon.pull_delay = 0.2
    launcher = DockerLauncher(_host(daemon), CONTROL)
    await asyncio.gather(
        *(launcher.start(f"s-{n}", f"b-{n}", "img:1", "prplos") for n in range(3))
    )
    assert daemon.pulls == ["img:1"]


async def test_a_hung_pull_neither_blocks_other_calls_nor_trips_the_breaker(
    fake_daemon: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(docker_host, "_OUTER_MARGIN", 0.05)
    daemon = fake_daemon(pullable={"img:1": "sha256:p"})
    daemon.pull_hang = threading.Event()
    host = _host(daemon, timeout=0.2)
    launcher = DockerLauncher(host, CONTROL, pull_timeout=0.3)
    creates = [
        asyncio.create_task(launcher.start(f"s-{n}", f"b-{n}", "img:1", "prplos"))
        for n in range(4)
    ]
    await asyncio.sleep(0.05)
    started = time.monotonic()
    assert await host.ping() is True
    assert time.monotonic() - started < 0.2
    results = await asyncio.gather(*creates, return_exceptions=True)
    assert all(isinstance(result, HostUnreachable) for result in results)
    assert not host.is_down
    daemon.pull_hang.set()
    host.close()


# Important 3: created-but-not-started rivals count, and listing tolerates removals.


async def test_a_young_created_rival_wins_the_race(fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    original_create = daemon.containers.create

    def create_with_rival(image: str, **kwargs: Any) -> Any:
        daemon.add_agent(
            session_id="s-rival",
            board_name="b1",
            control_id="c-other",
            status="created",
            created="2026-09-30T09:59:59.9Z",
        )
        return original_create(image, **kwargs)

    daemon.containers.create = create_with_rival
    with pytest.raises(BoardBusyOnHost):
        await DockerLauncher(_host(daemon), CONTROL).start(
            "s-1", "b1", "img:1", "prplos"
        )
    assert [c.labels["boardfarm.session_id"] for c in daemon.agents()] == ["s-rival"]


async def test_a_stale_created_leftover_does_not_block_the_board(
    fake_daemon: Any,
) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    daemon.add_agent(
        session_id="s-old",
        board_name="b1",
        control_id="c-other",
        status="created",
        created="2026-09-30T09:00:00Z",
    )
    info = await DockerLauncher(_host(daemon), CONTROL).start(
        "s-1", "b1", "img:1", "prplos"
    )
    assert info.session_id == "s-1"


async def test_listing_survives_a_container_removed_mid_list(fake_daemon: Any) -> None:
    daemon = fake_daemon()
    daemon.add_agent(session_id="s-1", board_name="b1", control_id=CONTROL)
    gone = daemon.add_agent(session_id="s-2", board_name="b2", control_id=CONTROL)
    daemon.vanish.add(gone.id)
    sessions = await DockerLauncher(_host(daemon), CONTROL).list_sessions()
    assert [info.session_id for info in sessions] == ["s-1"]


# Important 4: failures after create leave no ghost container behind.


async def test_a_failed_start_leaves_no_container(fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    daemon.fail["start"] = docker.errors.APIError("port is already allocated")
    with pytest.raises(docker.errors.APIError):
        await DockerLauncher(_host(daemon), CONTROL).start(
            "s-1", "b1", "img:1", "prplos"
        )
    assert daemon.agents() == []


async def test_unconfirmed_cleanup_is_recorded_and_finished_by_the_reconciler(
    world: _World,
) -> None:
    daemon = world.daemon
    daemon.fail["start"] = requests.exceptions.ConnectionError("reset")
    daemon.fail["remove"] = requests.exceptions.ConnectionError("reset")
    with pytest.raises(StopPending):
        await world.launcher.start("s-1", "b1", "img:1", "prplos", host="lab-1")
    assert world.launcher.entry("s-1").info.stop_pending is True
    world.hosts.docker_host("lab-1")._failures = 0  # as a reconciler ping would
    await world.reconciler.reconcile_host("lab-1")
    assert daemon.agents() == []
    assert world.launcher.entry("s-1") is None


# Important 5: startup must not finish pending stops (that can take minutes).


async def test_startup_defers_finishing_pending_stops(world: _World) -> None:
    world.daemon.add_agent(session_id="s-1", board_name="b1", control_id=CONTROL)
    [seen] = await world.launcher.list_host_sessions("lab-1")
    world.launcher.record(
        seen.model_copy(update={"state": "dead", "stop_pending": True, "ended_at": 5.0})
    )
    await world.reconciler.startup()
    assert world.registry.get("s-1").stop_pending is True
    assert len(world.daemon.agents("b1")) == 1
    await world.reconciler.reconcile_host("lab-1")
    assert world.registry.get("s-1") is None


# Important 6: a slow host must not delay the other hosts' passes.


async def test_a_slow_host_does_not_delay_the_others(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    release = asyncio.Event()

    async def reconcile_host(name: str) -> None:
        calls.append(name)
        if name == "slow":
            await release.wait()

    monkeypatch.setattr(world.hosts, "names", lambda: ["fast", "slow"])
    monkeypatch.setattr(world.reconciler, "reconcile_host", reconcile_host)
    loop_task = asyncio.create_task(world.reconciler.run(0.02))
    await asyncio.sleep(0.3)
    loop_task.cancel()
    release.set()
    with contextlib.suppress(asyncio.CancelledError):
        await loop_task
    assert calls.count("fast") >= 5
    assert calls.count("slow") == 1


# Important 7: host changes must be fenced against in-flight work.


async def test_close_lets_a_queued_call_finish(fake_daemon: Any) -> None:
    host = _host(fake_daemon(), workers=1)
    gate = threading.Event()
    running = asyncio.create_task(host.call(lambda _client: gate.wait(2)))
    queued = asyncio.create_task(host.call(lambda _client: "done"))
    await asyncio.sleep(0.05)
    host.close()
    gate.set()
    assert await queued == "done"
    await running


def test_a_cancelled_launch_releases_the_lease() -> None:
    class _Cancelled(FakeLauncher):
        async def start(self, *_args: Any, **_kwargs: Any) -> AgentInfo:
            raise asyncio.CancelledError

    app = create_app(_Cancelled(), {"prplos": "img"})
    with pytest.raises(BaseException):  # noqa: PT011, B017
        TestClient(app).post(
            "/sessions",
            json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}},
        )
    assert app.state.lease.held_by("b1") is None


async def test_a_forgotten_session_is_not_recorded_again_by_a_failing_stop(
    world: _World,
) -> None:
    await world.launcher.start("s-1", "b1", "img:1", "prplos", host="lab-1")

    class _ForgetThenFail:
        async def stop(self, session_id: str, *, remove: bool = True) -> None:  # noqa: ARG002
            world.launcher.forget(session_id)  # an admin force-delete lands mid-stop
            msg = "gone"
            raise HostUnreachable(msg, host="lab-1")

    world.launcher.launcher_for = lambda _host: _ForgetThenFail()
    with pytest.raises(StopPending):
        await world.launcher.stop("s-1")
    assert world.launcher.entry("s-1") is None


def test_index_only_entries_keep_a_host_in_use_and_force_forgets_them(
    tmp_path: Path, fake_daemon: Any
) -> None:
    daemon = fake_daemon()
    hosts = HostRegistry.load(
        tmp_path / "hosts.json",
        seed={"lab-1": {"docker_url": "tcp://10.0.0.1:2375", "default": True}},
        host_factory=lambda name, spec: DockerHost(
            name, spec, client_factory=daemon.client_factory
        ),
    )
    launcher = MultiHostLauncher(hosts, CONTROL, tmp_path / "sessions.json")
    launcher.record(
        AgentInfo(
            session_id="s-ghost",
            board_name="b1",
            runtime_profile="prplos",
            container_id="",
            host_port=0,
            created_at=0.0,
            host="lab-1",
            state="dead",
            stop_pending=True,
        )
    )
    client = TestClient(create_app(launcher, {"prplos": "img:1"}))
    assert client.delete("/admin/hosts/lab-1").status_code == 409
    forced = client.delete("/admin/hosts/lab-1?force=true")
    assert forced.status_code == 200, forced.text
    assert forced.json()["abandoned"] == ["s-ghost"]
    assert launcher.entry("s-ghost") is None
    hosts.close()
