"""Launcher that runs agents as Docker containers."""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from boardfarm3_control.launcher._common import (
    _DEFAULT_ARTIFACT_ROOT,
    _artifact_root,
    _free_port,
)

if TYPE_CHECKING:
    from boardfarm3_control.models import AgentInfo

_log = logging.getLogger(__name__)


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


class DockerLauncher:
    """Production launcher using docker-py (sync calls run in asyncio executor)."""

    _LABEL_SESSION = "boardfarm.session_id"
    _LABEL_BOARD = "boardfarm.board_name"
    _LABEL_PROFILE = "boardfarm.runtime_profile"
    _LABEL_CREATED = "boardfarm.created_at"
    _LABEL_ARTIFACT_DIR = "boardfarm.artifact_dir"

    def __init__(self, client: object | None = None) -> None:
        """Initialise with an optional pre-built docker client.

        :param client: docker.DockerClient instance; created from env if None
        :type client: object | None
        """
        import docker as _docker  # noqa: PLC0415

        self._client = client or _docker.from_env()

    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,
        runtime_profile: str,
        agent_env: dict[str, str] | None = None,
    ) -> AgentInfo:
        """Start a Docker container for a new agent session.

        :param session_id: unique session identifier
        :type session_id: str
        :param board_name: board this agent will own
        :type board_name: str
        :param image: Docker image to run
        :type image: str
        :param runtime_profile: profile key stored as label
        :type runtime_profile: str
        :param agent_env: extra environment variables to inject into the container
        :type agent_env: dict[str, str] | None
        :return: agent container info
        :rtype: AgentInfo
        """
        from boardfarm3_control.models import AgentInfo  # noqa: PLC0415

        host_port = _free_port()
        created_at = time.time()
        artifact_root = _artifact_root(agent_env)
        loop = asyncio.get_running_loop()

        def _start() -> object:
            return self._client.containers.run(
                image,
                detach=True,
                ports={"8000/tcp": host_port},
                labels={
                    self._LABEL_SESSION: session_id,
                    self._LABEL_BOARD: board_name,
                    self._LABEL_PROFILE: runtime_profile,
                    self._LABEL_CREATED: str(created_at),
                    # Persisted as a label, not just an env var, so a restart
                    # can recover it from list_sessions() alone (Docker
                    # labels survive a container restart; recomputing the
                    # override from agent_env would require it, which is not
                    # otherwise stored anywhere on the control plane).
                    self._LABEL_ARTIFACT_DIR: artifact_root,
                },
                environment={
                    "BOARDFARM_SESSION_ID": session_id,
                    "BOARDFARM_BOARD_NAME": board_name,
                    "BOARDFARM_AGENT_PORT": "8000",
                    **(agent_env or {}),
                },
            )

        container = await loop.run_in_executor(None, _start)
        return AgentInfo(
            session_id=session_id,
            board_name=board_name,
            runtime_profile=runtime_profile,
            container_id=container.id,
            host_port=host_port,
            created_at=created_at,
            pid=None,
            agent_url=f"http://localhost:{host_port}",
            artifact_dir=artifact_root,
        )

    def _find(self, session_id: str) -> list[Any]:
        """Return every container for a session, running or not.

        :param session_id: session to look up
        :type session_id: str
        :return: matching containers
        :rtype: list[typing.Any]
        """
        return self._client.containers.list(
            all=True,
            filters={"label": f"{self._LABEL_SESSION}={session_id}"},
        )

    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        """Stop the container, and remove it only when *remove* is set.

        A stopped container releases every tty and socket the agent held, so a
        retained corpse can never contend with a fresh session on the board.

        :param session_id: session whose container to stop
        :type session_id: str
        :param remove: also ``docker rm`` the container
        :type remove: bool
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, self._find, session_id)
        for container in containers:
            await loop.run_in_executor(None, container.stop)
            if remove:
                await loop.run_in_executor(None, container.remove)

    async def purge(self, session_id: str) -> None:
        """Remove the stopped container for a session.

        :param session_id: session whose container to remove
        :type session_id: str
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, self._find, session_id)
        for container in containers:
            await loop.run_in_executor(
                None,
                functools.partial(container.remove, force=True),
            )

    async def capture_logs(self, session_id: str) -> bytes:
        """Return the container's stdout and stderr.

        A daemon API call, so it works against a remote host and a stopped
        container alike.

        :param session_id: session whose logs to capture
        :type session_id: str
        :return: log bytes, empty when the container is gone
        :rtype: bytes
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, self._find, session_id)
        if not containers:
            return b""
        return await loop.run_in_executor(
            None,
            lambda: containers[0].logs(stdout=True, stderr=True),
        )

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return a tar of *path* from inside the container.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: path inside the container
        :type path: str
        :return: tar bytes, empty when unavailable
        :rtype: bytes
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, self._find, session_id)
        if not containers:
            return b""

        def _archive() -> bytes:
            stream, _ = containers[0].get_archive(path)
            return b"".join(stream)

        try:
            return await loop.run_in_executor(None, _archive)
        except Exception:  # noqa: BLE001
            _log.warning(
                "could not archive %s from session %s",
                path,
                session_id,
            )
            return b""

    async def list_sessions(self) -> list[AgentInfo]:
        """Return info for every container with a boardfarm.session_id label.

        Includes stopped containers so a failed agent's evidence remains
        visible until it is explicitly purged.

        :return: agent infos rebuilt from Docker container labels
        :rtype: list[AgentInfo]
        """
        from boardfarm3_control.models import AgentInfo  # noqa: PLC0415

        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(
            None,
            lambda: self._client.containers.list(
                all=True,
                filters={"label": self._LABEL_SESSION},
            ),
        )
        result = []
        for container in containers:
            labels = container.labels
            port_bindings = container.ports.get("8000/tcp") or [{}]
            host_port = int(port_bindings[0].get("HostPort", 0))
            is_running = container.status == "running"
            result.append(
                AgentInfo(
                    session_id=labels[self._LABEL_SESSION],
                    board_name=labels[self._LABEL_BOARD],
                    runtime_profile=labels[self._LABEL_PROFILE],
                    container_id=container.id,
                    host_port=host_port,
                    created_at=float(labels.get(self._LABEL_CREATED, 0)),
                    pid=None,
                    agent_url=f"http://localhost:{host_port}",
                    state="live" if is_running else "dead",
                    # None for a running container; every corpse must carry a
                    # real timestamp or it becomes permanently unreapable
                    # after a restart (SessionRegistry.rebuild() only ever
                    # consults the launcher, never the store).
                    ended_at=None if is_running else _finished_at(container),
                    artifact_dir=labels.get(
                        self._LABEL_ARTIFACT_DIR,
                        _DEFAULT_ARTIFACT_ROOT,
                    ),
                ),
            )
        return result
