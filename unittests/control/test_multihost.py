"""MultiHostLauncher: routing by host and the persisted sessions.json index."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import pytest

from boardfarm3_control.errors import HostUnreachable, NoHostForBoard, StopPending
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher import MultiHostLauncher
from boardfarm3_control.launcher.docker_host import DockerHost

if TYPE_CHECKING:
    from pathlib import Path


def _multihost(tmp_path: Path, daemons: dict[str, Any]) -> MultiHostLauncher:
    seed = {
        name: {"docker_url": f"tcp://10.0.0.{index}:2375"}
        for index, name in enumerate(sorted(daemons), start=1)
    }
    hosts = HostRegistry.load(
        tmp_path / "hosts.json",
        seed=seed,
        host_factory=lambda name, spec: DockerHost(
            name, spec, client_factory=daemons[name].client_factory
        ),
    )
    return MultiHostLauncher(hosts, "c-test", tmp_path / "sessions.json")


def _two_hosts(fake_daemon: Any) -> dict[str, Any]:
    return {
        name: fake_daemon(images={"img:1": "sha256:a"}) for name in ("lab-1", "lab-2")
    }


async def test_start_places_the_agent_on_the_named_host(
    tmp_path: Path, fake_daemon: Any
) -> None:
    daemons = _two_hosts(fake_daemon)
    launcher = _multihost(tmp_path, daemons)
    info = await launcher.start("s-1", "board-1", "img:1", "prplos", host="lab-2")
    assert info.host == "lab-2"
    assert info.agent_url.startswith("http://10.0.0.2:")
    assert daemons["lab-1"].runs == []
    assert len(daemons["lab-2"].runs) == 1
    assert launcher.entry("s-1").info == info
    launcher.hosts.close()


async def test_start_without_a_host_raises_no_host_for_board(
    tmp_path: Path, fake_daemon: Any
) -> None:
    launcher = _multihost(tmp_path, {"lab-1": fake_daemon()})
    with pytest.raises(NoHostForBoard):
        await launcher.start("s-1", "board-1", "img:1", "prplos")
    launcher.hosts.close()


async def test_index_survives_a_restart(tmp_path: Path, fake_daemon: Any) -> None:
    daemons = {"lab-1": fake_daemon(images={"img:1": "sha256:a"})}
    first = _multihost(tmp_path, daemons)
    info = await first.start("s-1", "board-1", "img:1", "prplos", host="lab-1")
    first.hosts.close()
    second = _multihost(tmp_path, daemons)
    assert second.entry("s-1").info == info
    saved = json.loads((tmp_path / "sessions.json").read_text())
    assert saved["version"] == 1
    assert list(saved["sessions"]) == ["s-1"]
    second.hosts.close()


async def test_stop_that_cannot_be_confirmed_is_recorded_as_pending(
    tmp_path: Path, fake_daemon: Any
) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    launcher = _multihost(tmp_path, {"lab-1": daemon})
    await launcher.start("s-1", "board-1", "img:1", "prplos", host="lab-1")
    daemon.down = True
    with pytest.raises(StopPending) as err:
        await launcher.stop("s-1")
    assert err.value.host == "lab-1"
    entry = launcher.entry("s-1")
    assert entry.info.stop_pending is True
    assert entry.info.state == "dead"
    assert entry.retained is False
    launcher.hosts.close()


async def test_stop_with_retain_keeps_a_retained_corpse(
    tmp_path: Path, fake_daemon: Any
) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    launcher = _multihost(tmp_path, {"lab-1": daemon})
    await launcher.start("s-1", "board-1", "img:1", "prplos", host="lab-1")
    await launcher.stop("s-1", remove=False)
    entry = launcher.entry("s-1")
    assert entry.retained is True
    assert entry.info.state == "dead"
    assert entry.info.stop_pending is False
    assert daemon.agents("board-1")[0].status == "exited"
    launcher.hosts.close()


async def test_stop_removes_the_index_entry(tmp_path: Path, fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    launcher = _multihost(tmp_path, {"lab-1": daemon})
    await launcher.start("s-1", "board-1", "img:1", "prplos", host="lab-1")
    await launcher.stop("s-1")
    assert launcher.entry("s-1") is None
    assert daemon.agents() == []
    launcher.hosts.close()


async def test_purge_on_a_down_host_keeps_the_entry(
    tmp_path: Path, fake_daemon: Any
) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:a"})
    launcher = _multihost(tmp_path, {"lab-1": daemon})
    await launcher.start("s-1", "board-1", "img:1", "prplos", host="lab-1")
    daemon.down = True
    with pytest.raises(HostUnreachable):
        await launcher.purge("s-1")
    assert launcher.entry("s-1") is not None
    daemon.down = False
    await launcher.purge("s-1")
    assert launcher.entry("s-1") is None
    assert daemon.agents() == []
    launcher.hosts.close()


async def test_list_sessions_falls_back_to_the_index_for_unreachable_hosts(
    tmp_path: Path, fake_daemon: Any
) -> None:
    daemons = _two_hosts(fake_daemon)
    launcher = _multihost(tmp_path, daemons)
    await launcher.start("s-1", "b1", "img:1", "prplos", host="lab-1")
    await launcher.start("s-2", "b2", "img:1", "prplos", host="lab-2")
    daemons["lab-2"].down = True
    sessions = {info.session_id: info.host for info in await launcher.list_sessions()}
    assert sessions == {"s-1": "lab-1", "s-2": "lab-2"}
    launcher.hosts.close()


async def test_capture_routes_to_the_session_host(
    tmp_path: Path, fake_daemon: Any
) -> None:
    launcher = _multihost(tmp_path, _two_hosts(fake_daemon))
    await launcher.start("s-1", "b1", "img:1", "prplos", host="lab-2")
    assert await launcher.capture_logs("s-1") == b"logs:s-1"
    assert await launcher.capture_logs("s-unknown") == b""
    launcher.hosts.close()


def test_corrupt_index_is_ignored(
    tmp_path: Path, fake_daemon: Any, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "sessions.json").write_text("{not json")
    with caplog.at_level(logging.WARNING):
        launcher = _multihost(tmp_path, {"lab-1": fake_daemon()})
    assert launcher.entries() == []
    assert "unreadable" in caplog.text
    launcher.hosts.close()
