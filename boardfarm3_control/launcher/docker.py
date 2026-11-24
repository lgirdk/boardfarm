"""Launcher that runs agent containers on one Docker host."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from boardfarm3_control.errors import (
    BoardBusyOnHost,
    ImagePullFailed,
    StopPending,
)
from boardfarm3_control.launcher._common import _DEFAULT_ARTIFACT_ROOT, _artifact_root

if TYPE_CHECKING:
    import httpx

    from boardfarm3_control.launcher.docker_host import DockerHost
    from boardfarm3_control.models import AgentInfo

_log = logging.getLogger(__name__)

# Container statuses in which an agent may still hold the board's consoles.
BUSY_STATUSES = ("running", "paused", "restarting")
DEFAULT_PULL_TIMEOUT = 600.0
_STOP_GRACE = 10.0
_ARCHIVE_TIMEOUT = 300.0
# A created-but-never-started container younger than this still counts as a
# rival in the re-check (another control plane may be about to start it).
_CREATED_GRACE_NS = 60 * 1_000_000_000


def _container_options() -> dict[str, Any]:
    """Return log rotation, always, and the resource limits and shared memory the environment sets.

    Docker's default json-file driver never rotates, so a chatty agent would
    fill the lab host's disk. Limits are opt-in because they depend on the lab.

    :return: extra keyword arguments for ``containers.create``
    :rtype: dict[str, Any]
    """
    options: dict[str, Any] = {
        "log_config": {
            "type": "json-file",
            "config": {
                "max-size": os.environ.get("BOARDFARM_AGENT_LOG_MAX_SIZE", "50m"),
                "max-file": os.environ.get("BOARDFARM_AGENT_LOG_MAX_FILE", "3"),
            },
        },
    }
    if memory := os.environ.get("BOARDFARM_AGENT_MEM_LIMIT", "").strip():
        options["mem_limit"] = memory
    if pids := os.environ.get("BOARDFARM_AGENT_PIDS_LIMIT", "").strip():
        options["pids_limit"] = int(pids)
    if cpus := os.environ.get("BOARDFARM_AGENT_CPUS", "").strip():
        options["nano_cpus"] = int(float(cpus) * 1_000_000_000)
    if shm := os.environ.get("BOARDFARM_AGENT_SHM_SIZE", "").strip():
        # GUI tests run browsers, which crash in Docker's default 64 MB /dev/shm.
        options["shm_size"] = shm
    return options


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


def _ended_at(container: Any) -> float | None:  # noqa: ANN401
    # A container that never started has no FinishedAt; use its Created time
    # so the reaper can still purge it.
    finished = _finished_at(container)
    if finished is not None or container.status != "created":
        return finished
    created = _created_ns(container)
    return created / 1_000_000_000 if created else None


def _published_port(_client: Any, container: Any) -> int | None:  # noqa: ANN401
    container.reload()
    for binding in container.ports.get("8000/tcp") or []:
        if binding.get("HostPort"):
            return int(binding["HostPort"])
    return None


def _created_ns(container: Any) -> int:  # noqa: ANN401
    # Go trims trailing zeros from RFC 3339 fractions (".1Z" vs ".12Z"), so
    # Docker's Created strings must be compared as numbers, never as text.
    raw = str(container.attrs.get("Created", ""))
    head, _, fraction = raw.removesuffix("Z").partition(".")
    try:
        seconds = int(datetime.fromisoformat(f"{head}+00:00").timestamp())
    except ValueError:
        return 0
    digits = "".join(ch for ch in fraction if ch.isdigit())[:9]
    return seconds * 1_000_000_000 + int(digits.ljust(9, "0"))


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
    _LABEL_MODE = "boardfarm.mode"
    _LABEL_CREATED_BY = "boardfarm.created_by"

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
        mode: str = "interact",
        created_by: str | None = None,
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
        :param mode: the session's mode, recorded so a restarted control plane knows it
        :type mode: str
        :param created_by: identity of the user who triggered this session
        :type created_by: str | None
        :return: the agent's info
        :rtype: AgentInfo
        :raises RuntimeError: when Docker published no port for the agent
        :raises StopPending: when a failed launch could not remove its container
        :raises BoardBusyOnHost: when the board already has a busy agent on this host
        :raises ImagePullFailed: when the image is missing and cannot be pulled

        # noqa: DAR402 BoardBusyOnHost ImagePullFailed
        """
        from boardfarm3_control.models import AgentInfo  # noqa: PLC0415

        del host
        await self._ensure_not_busy(board_name)
        ref = self._host.image_ref(image)
        image_id = await self._ensure_image(ref)
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
            self._LABEL_MODE: mode,
            **({self._LABEL_CREATED_BY: created_by} if created_by is not None else {}),
        }
        # Identity last: agent_env may add variables, never re-point the agent.
        environment = {
            **(agent_env or {}),
            "BOARDFARM_SESSION_ID": session_id,
            "BOARDFARM_BOARD_NAME": board_name,
            "BOARDFARM_AGENT_PORT": "8000",
        }
        # (bind_addr, None): Docker picks a free port on the host that owns it.
        ports = {"8000/tcp": (self._host.spec.bind_addr, None)}
        options = _container_options()

        def _create(client: Any) -> Any:  # noqa: ANN401
            return client.containers.create(
                ref,
                ports=ports,
                labels=labels,
                environment=environment,
                **options,
            )

        container = await self._host.call(_create)
        try:
            # Re-check before starting: a rival that is only created is still
            # a rival, and a loser that never started never touched the board.
            await self._recheck(board_name, container)
            await self._host.call(lambda _client: container.start())
            port = await self._host.call(_published_port, container)
            if port is None:
                msg = f"agent container {container.id} on host {self._host.name} has no published port"
                raise RuntimeError(msg)  # noqa: TRY301
        except BaseException as exc:
            removed = await self._remove_quietly(container)
            if not removed and not isinstance(exc, asyncio.CancelledError):
                # The container may still exist; the caller records a pending
                # stop so the reconciler removes it once the host answers.
                raise StopPending(session_id, self._host.name) from exc
            raise
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
            image_id=image_id,
            mode=mode,
            created_by=created_by,
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
                    # v=True: an image's VOLUMEs become anonymous volumes that
                    # outlive the container otherwise.
                    container.remove(v=True)

        await self._host.call(_stop, timeout=self._host.timeout + _STOP_GRACE)

    async def purge(self, session_id: str) -> None:
        """Force-remove this control plane's container for a session.

        :param session_id: session whose container to remove
        :type session_id: str
        """

        def _purge(client: Any) -> None:  # noqa: ANN401
            for container in self._find(client, session_id):
                container.remove(force=True, v=True)

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
        except Exception:  # noqa: BLE001
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
            return await self._host.call(_archive, timeout=_ARCHIVE_TIMEOUT, long=True)
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
                ignore_removed=True,
                filters={
                    "label": [
                        self._LABEL_SESSION,
                        f"{self._LABEL_CONTROL}={self._control_id}",
                    ],
                },
            )

        return [self._to_info(container) for container in await self._host.call(_list)]

    def _busy_for_board(self, client: Any, board_name: str) -> list[Any]:  # noqa: ANN401
        # Any control plane's agent counts: another control's agent still
        # holds the board's consoles.
        return client.containers.list(
            all=True,
            ignore_removed=True,
            filters={
                "label": [f"{self._LABEL_BOARD}={board_name}"],
                "status": list(BUSY_STATUSES),
            },
        )

    def _busy_error(self, board_name: str, other: Any) -> BoardBusyOnHost:  # noqa: ANN401
        msg = (
            f"board {board_name} already has a running agent on host {self._host.name}"
        )
        return BoardBusyOnHost(
            msg,
            host=self._host.name,
            container_id=other.id,
            control_id=other.labels.get(self._LABEL_CONTROL),
            session_id=other.labels.get(self._LABEL_SESSION),
        )

    async def _ensure_not_busy(self, board_name: str) -> None:
        busy = await self._host.call(self._busy_for_board, board_name)
        if busy:
            raise self._busy_error(board_name, busy[0])

    async def _ensure_image(self, ref: str) -> str:
        import docker.errors  # noqa: PLC0415

        def _get_or_pull(client: Any) -> str:  # noqa: ANN401
            try:
                return client.images.get(ref).id
            except docker.errors.ImageNotFound:
                return client.images.pull(ref).id

        try:
            return await self._host.single_flight(
                f"pull:{ref}",
                lambda: self._host.call(
                    _get_or_pull, timeout=self._pull_timeout, long=True
                ),
            )
        except docker.errors.APIError as exc:
            msg = f"could not pull {ref} on host {self._host.name}: {exc}"
            raise ImagePullFailed(msg, host=self._host.name, image=ref) from exc

    def _contenders(self, client: Any, board_name: str) -> list[Any]:  # noqa: ANN401
        return client.containers.list(
            all=True,
            ignore_removed=True,
            filters={
                "label": [f"{self._LABEL_BOARD}={board_name}"],
                "status": [*BUSY_STATUSES, "created"],
            },
        )

    async def _recheck(self, board_name: str, ours: Any) -> None:  # noqa: ANN401
        # Two control planes can pass the busy check at the same moment. Both
        # launches land on this daemon (boards are pinned), so the earliest
        # Created wins; start() removes a loser's container before it starts.
        contenders = await self._host.call(self._contenders, board_name)
        horizon = _created_ns(ours) - _CREATED_GRACE_NS
        rivals = [
            c
            for c in contenders
            if c.id == ours.id or c.status in BUSY_STATUSES or _created_ns(c) >= horizon
        ]
        ranked = sorted(rivals, key=lambda c: (_created_ns(c), c.id))
        if ranked and ranked[0].id != ours.id:
            raise self._busy_error(board_name, ranked[0])

    def _find(self, client: Any, session_id: str) -> list[Any]:  # noqa: ANN401
        return client.containers.list(
            all=True,
            ignore_removed=True,
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
            ended_at=None if busy else _ended_at(container),
            artifact_dir=labels.get(self._LABEL_ARTIFACT_DIR, _DEFAULT_ARTIFACT_ROOT),
            host=self._host.name,
            image_id=container.attrs.get("Image"),
            mode=labels.get(self._LABEL_MODE, "interact"),
            created_by=labels.get(self._LABEL_CREATED_BY),
        )

    async def _remove_quietly(self, container: Any) -> bool:  # noqa: ANN401
        try:
            await self._host.call(lambda _client: container.remove(force=True, v=True))
        except Exception:  # noqa: BLE001
            _log.warning(
                "could not remove container %s on host %s",
                container.id,
                self._host.name,
            )
            return False
        return True

    def agent_client(self, info: AgentInfo) -> httpx.AsyncClient | None:  # noqa: ARG002
        """Use the control plane's shared pool for every agent.

        :param info: the session's agent info
        :type info: AgentInfo
        :return: None, meaning the shared pooled client
        :rtype: httpx.AsyncClient | None
        """
        return None
