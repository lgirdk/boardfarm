"""DockerLauncher against one fake Docker host."""

from __future__ import annotations

from typing import Any

import pytest

from boardfarm3_control.errors import BoardBusyOnHost, ImagePullFailed
from boardfarm3_control.launcher.docker import DockerLauncher, _created_ns
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.models import HostSpec

CONTROL = "c-test"


def _launcher(daemon: Any, **spec: Any) -> DockerLauncher:
    host = DockerHost(
        "lab-1",
        HostSpec(docker_url="tcp://10.0.0.5:2375", **spec),
        client_factory=daemon.client_factory,
    )
    return DockerLauncher(host, CONTROL)


async def test_start_uses_docker_assigned_port_and_advertise_addr(
    fake_daemon: Any,
) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:aaa"})
    info = await _launcher(daemon).start("s-1", "board-1", "img:1", "prplos")
    run = daemon.runs[0]
    assert run["ports"] == {"8000/tcp": ("0.0.0.0", None)}  # noqa: S104
    assert run["labels"]["boardfarm.control_id"] == CONTROL
    assert run["environment"]["BOARDFARM_AGENT_PORT"] == "8000"
    assert info.host == "lab-1"
    assert info.host_port == 32768
    assert info.agent_url == "http://10.0.0.5:32768"
    assert info.image_id == "sha256:aaa"


async def test_start_publishes_on_bind_addr(fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:aaa"})
    await _launcher(daemon, bind_addr="10.0.0.5").start(
        "s-1", "board-1", "img:1", "prplos"
    )
    assert daemon.runs[0]["ports"] == {"8000/tcp": ("10.0.0.5", None)}


async def test_start_runs_the_registry_resolved_image(fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"mirror:5000/img:1": "sha256:bbb"})
    await _launcher(daemon, registry="mirror:5000").start(
        "s-1", "board-1", "img:1", "prplos"
    )
    assert daemon.runs[0]["image"] == "mirror:5000/img:1"


async def test_start_records_artifact_dir_label(fake_daemon: Any) -> None:
    """A per-session BOARDFARM_ARTIFACT_DIR override must survive a restart."""
    daemon = fake_daemon(images={"img:1": "sha256:aaa"})
    info = await _launcher(daemon).start(
        "s-1",
        "board",
        "img:1",
        "prplos",
        agent_env={"BOARDFARM_ARTIFACT_DIR": "/custom/artifacts"},
    )
    assert info.artifact_dir == "/custom/artifacts"
    assert daemon.runs[0]["labels"]["boardfarm.artifact_dir"] == "/custom/artifacts"


async def test_start_without_a_published_port_removes_the_container(
    fake_daemon: Any,
) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:aaa"})
    daemon.publish = False
    with pytest.raises(RuntimeError, match="no published port"):
        await _launcher(daemon).start("s-1", "board-1", "img:1", "prplos")
    assert daemon.agents() == []


async def test_list_sessions_only_returns_this_control_plane(fake_daemon: Any) -> None:
    daemon = fake_daemon()
    daemon.add_agent(session_id="s-mine", board_name="b1", control_id=CONTROL)
    daemon.add_agent(session_id="s-other", board_name="b2", control_id="c-other")
    daemon.add_agent(session_id="s-legacy", board_name="b3", control_id=None)
    sessions = await _launcher(daemon).list_sessions()
    assert [info.session_id for info in sessions] == ["s-mine"]
    assert sessions[0].host == "lab-1"
    assert sessions[0].agent_url.startswith("http://10.0.0.5:")


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("running", "live"),
        ("paused", "live"),
        ("restarting", "live"),
        ("exited", "dead"),
        ("created", "dead"),
    ],
)
async def test_list_sessions_maps_busy_statuses_to_live(
    fake_daemon: Any, status: str, state: str
) -> None:
    daemon = fake_daemon()
    daemon.add_agent(
        session_id="s-1", board_name="b1", control_id=CONTROL, status=status
    )
    [info] = await _launcher(daemon).list_sessions()
    assert info.state == state
    assert (info.ended_at is None) == (state == "live")


async def test_list_sessions_unparseable_finished_at_is_none(fake_daemon: Any) -> None:
    daemon = fake_daemon()
    container = daemon.add_agent(
        session_id="s-1", board_name="b1", control_id=CONTROL, status="exited"
    )
    container.attrs["State"]["FinishedAt"] = "not-a-timestamp"
    [info] = await _launcher(daemon).list_sessions()
    assert info.state == "dead"
    assert info.ended_at is None


async def test_stop_and_purge_never_touch_foreign_containers(fake_daemon: Any) -> None:
    daemon = fake_daemon()
    daemon.add_agent(session_id="s-1", board_name="b1", control_id="c-other")
    launcher = _launcher(daemon)
    await launcher.stop("s-1")
    await launcher.purge("s-1")
    assert [container.status for container in daemon.agents()] == ["running"]


async def test_stop_keeps_or_removes_the_container(fake_daemon: Any) -> None:
    daemon = fake_daemon()
    daemon.add_agent(session_id="s-1", board_name="b1", control_id=CONTROL)
    daemon.add_agent(session_id="s-2", board_name="b2", control_id=CONTROL)
    launcher = _launcher(daemon)
    await launcher.stop("s-1", remove=False)
    await launcher.stop("s-2")
    remaining = {
        container.labels["boardfarm.session_id"]: container.status
        for container in daemon.agents()
    }
    assert remaining == {"s-1": "exited"}


async def test_capture_returns_empty_when_host_is_down(fake_daemon: Any) -> None:
    daemon = fake_daemon()
    daemon.add_agent(session_id="s-1", board_name="b1", control_id=CONTROL)
    launcher = _launcher(daemon)
    assert await launcher.capture_logs("s-1") == b"logs:s-1"
    daemon.down = True
    assert await launcher.capture_logs("s-1") == b""
    assert await launcher.capture_files("s-1", "/var/log/boardfarm/s-1") == b""


class _Created:
    def __init__(self, created: str) -> None:
        self.attrs = {"Created": created}


def test_created_ns_compares_numerically() -> None:
    assert _created_ns(_Created("2026-09-30T10:00:00.1Z")) < _created_ns(
        _Created("2026-09-30T10:00:00.12Z")
    )
    assert _created_ns(_Created("2026-09-30T10:00:01Z")) > _created_ns(
        _Created("2026-09-30T10:00:00.999999999Z")
    )
    assert _created_ns(_Created("garbage")) == 0


async def test_busy_board_blocks_launch_whoever_owns_it(fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:aaa"})
    daemon.add_agent(
        session_id="s-old", board_name="board-1", control_id="c-other", status="paused"
    )
    with pytest.raises(BoardBusyOnHost) as err:
        await _launcher(daemon).start("s-1", "board-1", "img:1", "prplos")
    assert err.value.fields["control_id"] == "c-other"
    assert err.value.fields["session_id"] == "s-old"
    assert daemon.runs == []


async def test_stopped_agent_does_not_block_launch(fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:aaa"})
    daemon.add_agent(
        session_id="s-old", board_name="board-1", control_id=CONTROL, status="exited"
    )
    info = await _launcher(daemon).start("s-1", "board-1", "img:1", "prplos")
    assert info.session_id == "s-1"


async def test_missing_image_is_pulled_before_run(fake_daemon: Any) -> None:
    daemon = fake_daemon(pullable={"img:1": "sha256:ppp"})
    info = await _launcher(daemon).start("s-1", "board-1", "img:1", "prplos")
    assert daemon.pulls == ["img:1"]
    assert info.image_id == "sha256:ppp"


async def test_present_image_is_not_pulled(fake_daemon: Any) -> None:
    daemon = fake_daemon(
        images={"img:1": "sha256:aaa"}, pullable={"img:1": "sha256:new"}
    )
    info = await _launcher(daemon).start("s-1", "board-1", "img:1", "prplos")
    assert daemon.pulls == []
    assert info.image_id == "sha256:aaa"


async def test_pull_failure_raises_image_pull_failed_and_runs_nothing(
    fake_daemon: Any,
) -> None:
    daemon = fake_daemon()
    launcher = _launcher(daemon)
    with pytest.raises(ImagePullFailed) as err:
        await launcher.start("s-1", "board-1", "img:1", "prplos")
    assert err.value.fields == {"host": "lab-1", "image": "img:1"}
    assert "manifest for img:1 not found" in err.value.message
    assert daemon.runs == []
    assert not launcher.host.is_down


async def test_recheck_loser_removes_its_own_container(fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:aaa"})
    original_create = daemon.containers.create

    def create_with_rival(image: str, **kwargs: Any) -> Any:
        daemon.add_agent(
            session_id="s-rival",
            board_name="board-1",
            control_id="c-other",
            created="2026-09-30T09:59:59.9Z",
        )
        return original_create(image, **kwargs)

    daemon.containers.create = create_with_rival
    with pytest.raises(BoardBusyOnHost) as err:
        await _launcher(daemon).start("s-1", "board-1", "img:1", "prplos")
    assert err.value.fields["session_id"] == "s-rival"
    assert [c.labels["boardfarm.session_id"] for c in daemon.agents()] == ["s-rival"]


async def test_recheck_winner_keeps_its_container(fake_daemon: Any) -> None:
    daemon = fake_daemon(images={"img:1": "sha256:aaa"})
    original_create = daemon.containers.create

    def create_with_later_rival(image: str, **kwargs: Any) -> Any:
        container = original_create(image, **kwargs)
        daemon.add_agent(
            session_id="s-rival",
            board_name="board-1",
            control_id="c-other",
            created="2026-09-30T11:00:00Z",
        )
        return container

    daemon.containers.create = create_with_later_rival
    info = await _launcher(daemon).start("s-1", "board-1", "img:1", "prplos")
    assert info.session_id == "s-1"
    assert len(daemon.agents("board-1")) == 2  # the rival's control removes its own
