"""Shared fixtures for control plane tests."""

from __future__ import annotations

import itertools
import time
from typing import TYPE_CHECKING, Any

import docker.errors
import pytest
import requests

from boardfarm3_control.launcher import FakeLauncher

if TYPE_CHECKING:
    import threading

_NEVER = "0001-01-01T00:00:00Z"
_STOPPED_AT = "2026-09-30T10:00:00.5Z"
_BUSY = ("running", "paused", "restarting")
_ANY_IP = "0.0.0.0"  # noqa: S104


@pytest.fixture
def fake_launcher() -> FakeLauncher:
    """Return a fresh FakeLauncher with no sessions."""
    return FakeLauncher()


@pytest.fixture
def profiles() -> dict[str, str]:
    """Return a minimal profile map for tests."""
    return {"prplos": "boardfarm3-agent:latest"}


class FakeContainer:
    """docker-py ``Container`` stand-in holding what DockerLauncher reads."""

    def __init__(  # noqa: PLR0913
        self,
        daemon: FakeDockerDaemon,
        container_id: str,
        *,
        labels: dict[str, str],
        created: str,
        image_id: str,
        host_port: int | None,
        bind_ip: str,
    ) -> None:
        """Create a running container."""
        self._daemon = daemon
        self.id = container_id
        self.bind_ip = bind_ip
        self.labels = dict(labels)
        self.status = "running"
        self.ports: dict[str, list[dict[str, str]]] = {}
        if host_port is not None:
            self.ports["8000/tcp"] = [{"HostIp": bind_ip, "HostPort": str(host_port)}]
        self.attrs: dict[str, Any] = {
            "Created": created,
            "Image": image_id,
            "State": {"FinishedAt": _NEVER},
        }

    def reload(self) -> None:
        """Refresh attributes (a daemon round trip)."""
        self._daemon.touch("reload")

    def start(self) -> None:
        """Start a created container; Docker assigns the published port now."""
        self._daemon.touch("start")
        self.status = "running"
        if self._daemon.publish:
            port = str(next(self._daemon.port_counter))
            self.ports["8000/tcp"] = [{"HostIp": self.bind_ip, "HostPort": port}]

    def stop(self, timeout: int | None = None) -> None:  # noqa: ARG002
        """Stop the container."""
        self._daemon.touch("stop")
        self.status = "exited"
        self.attrs["State"]["FinishedAt"] = _STOPPED_AT

    def remove(self, force: bool = False) -> None:  # noqa: ARG002
        """Remove the container."""
        self._daemon.touch("remove")
        self._daemon.store.pop(self.id, None)

    def logs(self, stdout: bool = True, stderr: bool = True) -> bytes:  # noqa: ARG002
        """Return canned logs."""
        self._daemon.touch("logs")
        return f"logs:{self.labels.get('boardfarm.session_id')}".encode()

    def get_archive(self, path: str) -> tuple[list[bytes], dict[str, Any]]:
        """Return a canned archive stream."""
        self._daemon.touch("archive")
        return [f"tar:{path}".encode()], {}


def _matches(container: FakeContainer, filters: dict[str, Any]) -> bool:
    labels = filters.get("label", [])
    for item in [labels] if isinstance(labels, str) else labels:
        key, sep, value = item.partition("=")
        if key not in container.labels or (sep and container.labels[key] != value):
            return False
    statuses = filters.get("status")
    if statuses:
        allowed = [statuses] if isinstance(statuses, str) else statuses
        if container.status not in allowed:
            return False
    return True


class _Containers:
    """``client.containers``."""

    def __init__(self, daemon: FakeDockerDaemon) -> None:
        """Bind to the daemon."""
        self._daemon = daemon

    def create(self, image: str, **kwargs: Any) -> FakeContainer:
        """Create a container (status ``created``, no port yet)."""
        daemon = self._daemon
        daemon.touch("create")
        daemon.runs.append({"image": image, **kwargs})
        bind_ip, _ = kwargs["ports"]["8000/tcp"]
        return daemon.add(
            labels=kwargs["labels"],
            image_id=daemon.images_present.get(image, "sha256:unknown"),
            bind_ip=bind_ip,
            status="created",
            publish=False,
        )

    def run(self, image: str, **kwargs: Any) -> FakeContainer:
        """Create, then start, like docker-py (a failed start leaves the container)."""
        kwargs.pop("detach", None)
        container = self.create(image, **kwargs)
        container.start()
        return container

    def list(
        self,
        all: bool = False,  # noqa: A002
        filters: dict[str, Any] | None = None,
        ignore_removed: bool = False,
    ) -> list[FakeContainer]:
        """List containers like docker-py: ids first, then one inspect each.

        A container in ``vanish`` is removed between the two steps; docker-py
        then raises NotFound unless ``ignore_removed`` is set.
        """
        self._daemon.touch("list")
        listed = [
            container
            for container in list(self._daemon.store.values())
            if (all or container.status == "running")
            and (not filters or _matches(container, filters))
        ]
        vanished = [c for c in listed if c.id in self._daemon.vanish]
        for container in vanished:
            self._daemon.store.pop(container.id, None)
            self._daemon.vanish.discard(container.id)
        if vanished and not ignore_removed:
            msg = f"No such container: {vanished[0].id}"
            raise docker.errors.NotFound(msg)
        return [c for c in listed if c not in vanished]


class _Image:
    """docker-py ``Image`` stand-in."""

    def __init__(self, image_id: str) -> None:
        """Remember the image id."""
        self.id = image_id


class _Images:
    """``client.images``."""

    def __init__(self, daemon: FakeDockerDaemon) -> None:
        """Bind to the daemon."""
        self._daemon = daemon

    def get(self, ref: str) -> _Image:
        """Return a present image or raise ImageNotFound."""
        self._daemon.touch("image_get")
        if ref not in self._daemon.images_present:
            msg = f"No such image: {ref}"
            raise docker.errors.ImageNotFound(msg)
        return _Image(self._daemon.images_present[ref])

    def pull(self, ref: str) -> _Image:
        """Pull a pullable image or raise APIError."""
        self._daemon.touch("pull")
        self._daemon.pulls.append(ref)
        if self._daemon.pull_hang is not None:
            self._daemon.pull_hang.wait(10)
        time.sleep(self._daemon.pull_delay)
        if ref not in self._daemon.pullable:
            msg = f"manifest for {ref} not found"
            raise docker.errors.APIError(msg)
        self._daemon.images_present[ref] = self._daemon.pullable[ref]
        return _Image(self._daemon.pullable[ref])


class FakeDockerDaemon:
    """An in-memory Docker daemon; pass ``client_factory`` to ``DockerHost``."""

    def __init__(
        self,
        *,
        images: dict[str, str] | None = None,
        pullable: dict[str, str] | None = None,
    ) -> None:
        """Create an empty daemon with the given images present or pullable."""
        self.store: dict[str, FakeContainer] = {}
        self.images_present = dict(images or {})
        self.pullable = dict(pullable or {})
        self.pulls: list[str] = []
        self.runs: list[dict[str, Any]] = []
        self.down = False
        self.publish = True
        self.hang: threading.Event | None = None
        self.pull_hang: threading.Event | None = None
        self.pull_delay = 0.0
        self.vanish: set[str] = set()
        self.fail: dict[str, Exception] = {}
        self._ids = itertools.count(1)
        self.port_counter = itertools.count(32768)
        self._ticks = itertools.count(1)
        self.containers = _Containers(self)
        self.images = _Images(self)

    def client_factory(self, _spec: object, _timeout: float) -> FakeDockerDaemon:
        """Act as docker-py client construction, which already talks to the daemon."""
        self.touch("connect")
        return self

    def touch(self, op: str) -> None:
        """Simulate one daemon round trip: hang, refuse, or fail as configured."""
        if self.hang is not None:
            self.hang.wait(10)
        if self.down:
            msg = "connection refused"
            raise requests.exceptions.ConnectionError(msg)
        if op in self.fail:
            raise self.fail.pop(op)

    def ping(self) -> bool:
        """Answer a ping."""
        self.touch("ping")
        return True

    def close(self) -> None:
        """Nothing to close."""

    def next_created(self) -> str:
        """Return a strictly increasing Docker-style Created timestamp."""
        tick = next(self._ticks)
        return f"2026-09-30T10:{tick // 60:02d}:{tick % 60:02d}.5Z"

    def add(  # noqa: PLR0913
        self,
        *,
        labels: dict[str, str],
        image_id: str = "sha256:img",
        bind_ip: str = _ANY_IP,
        created: str | None = None,
        status: str = "running",
        publish: bool = True,
    ) -> FakeContainer:
        """Put a container in the daemon directly (no round trip)."""
        container = FakeContainer(
            self,
            f"c{next(self._ids)}",
            labels=labels,
            created=created or self.next_created(),
            image_id=image_id,
            host_port=next(self.port_counter) if publish else None,
            bind_ip=bind_ip,
        )
        container.status = status
        if status in ("exited", "dead"):
            container.attrs["State"]["FinishedAt"] = _STOPPED_AT
        self.store[container.id] = container
        return container

    def add_agent(  # noqa: PLR0913
        self,
        *,
        session_id: str,
        board_name: str,
        control_id: str | None,
        status: str = "running",
        created: str | None = None,
        profile: str = "prplos",
    ) -> FakeContainer:
        """Put an agent container labelled like DockerLauncher's in the daemon."""
        labels = {
            "boardfarm.session_id": session_id,
            "boardfarm.board_name": board_name,
            "boardfarm.runtime_profile": profile,
            "boardfarm.created_at": "1.0",
        }
        if control_id is not None:
            labels["boardfarm.control_id"] = control_id
        return self.add(labels=labels, created=created, status=status)

    def agents(self, board_name: str | None = None) -> list[FakeContainer]:
        """Return the agent containers, optionally for one board."""
        return [
            container
            for container in self.store.values()
            if board_name is None
            or container.labels.get("boardfarm.board_name") == board_name
        ]


@pytest.fixture
def fake_daemon() -> type[FakeDockerDaemon]:
    """Return the FakeDockerDaemon class; call it once per simulated host."""
    return FakeDockerDaemon
