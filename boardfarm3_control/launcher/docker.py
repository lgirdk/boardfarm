"""Launcher that runs agent containers on one Docker host."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from boardfarm3_control.errors import HostUnreachable
from boardfarm3_control.launcher._common import _DEFAULT_ARTIFACT_ROOT, _artifact_root

if TYPE_CHECKING:
    from boardfarm3_control.launcher.docker_host import DockerHost
    from boardfarm3_control.models import AgentInfo

_log = logging.getLogger(__name__)

# Container statuses in which an agent may still hold the board's consoles.
BUSY_STATUSES = ("running", "paused", "restarting")
DEFAULT_PULL_TIMEOUT = 600.0
_STOP_GRACE = 10.0
_ARCHIVE_TIMEOUT = 300.0


def _finished_at(container: Any) -> float | None:  # noqa: ANN401
    """Parse a Docker container's ``State.FinishedAt`` to a Unix timestamp.

    Docker reports the zero value ``"0001-01-01T00:00:00Z"`` for a container
    that has never stopped, and emits nanosecond-precision fractional seconds
    that :func:`datetime.fromisoformat` cannot parse directly (it accepts at
    most microseconds).

    :param container: docker-py container object
    :type container: Any
    :return: Unix timestamp, or None when absent, zero, or unparseable
    :rtype: float | None
    """
    raw = container.attrs.get("State", {}).get("FinishedAt", "")
    if not raw or raw.startswith("0001-01-01"):
        return None
    if "." in raw:
        head, _, fractional_and_zone = raw.partition(".")
        fractional = fractional_and_zone.rstrip("Z")
        raw = f"{head}.{fractional[:6]}Z"
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        _log.warning("could not parse container FinishedAt %r", raw)
        return None


def _published_port(_client: Any, container: Any) -> int | None:  # noqa: ANN401
    container.reload()
    for binding in container.ports.get("8000/tcp") or []:
        if binding.get("HostPort"):
            return int(binding["HostPort"])
    return None


class DockerLauncher:
    """Runs agent containers on one Docker host, scoped to one control plane.

    Every list, stop, purge and capture is filtered by the
    ``boardfarm.control_id`` label, so containers another control plane
    launched on the same host are never adopted, stopped or reaped.
    """

    _LABEL_SESSION = "boardfarm.session_id"
    _LABEL_BOARD = "boardfarm.board_name"
    _LABEL_PROFILE = "boardfarm.runtime_profile"
    _LABEL_CREATED = "boardfarm.created_at"
    _LABEL_ARTIFACT_DIR = "boardfarm.artifact_dir"
    _LABEL_CONTROL = "boardfarm.control_id"

    def __init__(
        self,
        host: DockerHost,
        control_id: str,
        *,
        pull_timeout: float = DEFAULT_PULL_TIMEOUT,
    ) -> None:
        """Bind the launcher to one host and one control plane.

        :param host: the Docker host agents run on
        :type host: DockerHost
        :param control_id: this control plane's id (``boardfarm.control_id``)
        :type control_id: str
        :param pull_timeout: seconds allowed for pulling a missing image
        :type pull_timeout: float
        """
        self._host = host
        self._control_id = control_id
        self._pull_timeout = pull_timeout

    @property
    def host(self) -> DockerHost:
        """Return the host this launcher runs agents on.

        :return: the Docker host
        :rtype: DockerHost
        """
        return self._host

    async def start(  # noqa: PLR0913
        self,
        session_id: str,
        board_name: str,
        image: str,
        runtime_profile: str,
        agent_env: dict[str, str] | None = None,
        host: str | None = None,
    ) -> AgentInfo:
        """Start an agent container with a Docker-assigned host port.

        :param session_id: unique session identifier
        :type session_id: str
        :param board_name: board this agent will own
        :type board_name: str
        :param image: profile image, resolved against the host's registry
        :type image: str
        :param runtime_profile: profile key stored as a label
        :type runtime_profile: str
        :param agent_env: extra environment variables for the agent
        :type agent_env: dict[str, str] | None
        :param host: ignored; a DockerLauncher is bound to one host
        :type host: str | None
        :return: the agent's info
        :rtype: AgentInfo
        :raises RuntimeError: when Docker published no port for the agent
        """
        from boardfarm3_control.models import AgentInfo  # noqa: PLC0415

        del host
        ref = self._host.image_ref(image)
        created_at = time.time()
        artifact_root = _artifact_root(agent_env)
        labels = {
            self._LABEL_SESSION: session_id,
            self._LABEL_BOARD: board_name,
            self._LABEL_PROFILE: runtime_profile,
            self._LABEL_CREATED: str(created_at),
            # A label, not only an env var, so a restart recovers it from
            # list_sessions() alone: labels survive a container restart.
            self._LABEL_ARTIFACT_DIR: artifact_root,
            self._LABEL_CONTROL: self._control_id,
        }
        environment = {
            "BOARDFARM_SESSION_ID": session_id,
            "BOARDFARM_BOARD_NAME": board_name,
            "BOARDFARM_AGENT_PORT": "8000",
            **(agent_env or {}),
        }
        # (bind_addr, None): Docker picks a free port on the host that owns it.
        ports = {"8000/tcp": (self._host.spec.bind_addr, None)}

        def _run(client: Any) -> Any:  # noqa: ANN401
            return client.containers.run(
                ref,
                detach=True,
                ports=ports,
                labels=labels,
                environment=environment,
            )

        container = await self._host.call(_run)
        port = await self._host.call(_published_port, container)
        if port is None:
            await self._remove_quietly(container)
            msg = f"agent container {container.id} on host {self._host.name} has no published port"
            raise RuntimeError(msg)
        return AgentInfo(
            session_id=session_id,
            board_name=board_name,
            runtime_profile=runtime_profile,
            container_id=container.id,
            host_port=port,
            created_at=created_at,
            pid=None,
            agent_url=self._host.agent_url(port),
            artifact_dir=artifact_root,
            host=self._host.name,
            image_id=container.attrs.get("Image"),
        )

    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        """Stop this control plane's container for a session.

        :param session_id: session whose container to stop
        :type session_id: str
        :param remove: also remove the container, as ``docker rm`` would
        :type remove: bool
        """

        def _stop(client: Any) -> None:  # noqa: ANN401
            for container in self._find(client, session_id):
                container.stop()
                if remove:
                    container.remove()

        await self._host.call(_stop, timeout=self._host.timeout + _STOP_GRACE)

    async def purge(self, session_id: str) -> None:
        """Force-remove this control plane's container for a session.

        :param session_id: session whose container to remove
        :type session_id: str
        """

        def _purge(client: Any) -> None:  # noqa: ANN401
            for container in self._find(client, session_id):
                container.remove(force=True)

        await self._host.call(_purge)

    async def capture_logs(self, session_id: str) -> bytes:
        """Return the container's stdout and stderr through the Docker API.

        :param session_id: session whose logs to capture
        :type session_id: str
        :return: log bytes, empty when the container or the host is gone
        :rtype: bytes
        """

        def _logs(client: Any) -> bytes:  # noqa: ANN401
            containers = self._find(client, session_id)
            if not containers:
                return b""
            return containers[0].logs(stdout=True, stderr=True)

        try:
            return await self._host.call(_logs)
        except HostUnreachable:
            _log.warning(
                "host %s unreachable; no logs for %s", self._host.name, session_id
            )
            return b""

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return a tar of *path* from inside the container.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: path inside the container
        :type path: str
        :return: tar bytes, empty when unavailable
        :rtype: bytes
        """

        def _archive(client: Any) -> bytes:  # noqa: ANN401
            containers = self._find(client, session_id)
            if not containers:
                return b""
            stream, _ = containers[0].get_archive(path)
            return b"".join(stream)

        try:
            return await self._host.call(_archive, timeout=_ARCHIVE_TIMEOUT)
        except Exception:  # noqa: BLE001
            _log.warning(
                "could not archive %s from session %s on host %s",
                path,
                session_id,
                self._host.name,
            )
            return b""

    async def list_sessions(self) -> list[AgentInfo]:
        """Return every container this control plane launched on the host.

        Busy containers (running, paused, restarting) are ``live``; any other
        status is ``dead`` with ``ended_at`` from ``State.FinishedAt``.

        :return: agent infos rebuilt from container labels
        :rtype: list[AgentInfo]
        """

        def _list(client: Any) -> list[Any]:  # noqa: ANN401
            return client.containers.list(
                all=True,
                filters={
                    "label": [
                        self._LABEL_SESSION,
                        f"{self._LABEL_CONTROL}={self._control_id}",
                    ],
                },
            )

        return [self._to_info(container) for container in await self._host.call(_list)]

    def _find(self, client: Any, session_id: str) -> list[Any]:  # noqa: ANN401
        return client.containers.list(
            all=True,
            filters={
                "label": [
                    f"{self._LABEL_SESSION}={session_id}",
                    f"{self._LABEL_CONTROL}={self._control_id}",
                ],
            },
        )

    def _to_info(self, container: Any) -> AgentInfo:  # noqa: ANN401
        from boardfarm3_control.models import AgentInfo  # noqa: PLC0415

        labels = container.labels
        bindings = container.ports.get("8000/tcp") or [{}]
        host_port = int(bindings[0].get("HostPort") or 0)
        busy = container.status in BUSY_STATUSES
        return AgentInfo(
            session_id=labels[self._LABEL_SESSION],
            board_name=labels[self._LABEL_BOARD],
            runtime_profile=labels[self._LABEL_PROFILE],
            container_id=container.id,
            host_port=host_port,
            created_at=float(labels.get(self._LABEL_CREATED, 0)),
            pid=None,
            agent_url=self._host.agent_url(host_port),
            state="live" if busy else "dead",
            # None while busy; every corpse carries a real timestamp or it
            # becomes unreapable after a restart.
            ended_at=None if busy else _finished_at(container),
            artifact_dir=labels.get(self._LABEL_ARTIFACT_DIR, _DEFAULT_ARTIFACT_ROOT),
            host=self._host.name,
            image_id=container.attrs.get("Image"),
        )

    async def _remove_quietly(self, container: Any) -> None:  # noqa: ANN401
        try:
            await self._host.call(lambda _client: container.remove(force=True))
        except Exception:  # noqa: BLE001
            _log.warning(
                "could not remove container %s on host %s",
                container.id,
                self._host.name,
            )
