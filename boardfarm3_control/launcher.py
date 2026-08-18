"""Container lifecycle management for boardfarm agent sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from boardfarm3_control.models import AgentInfo

_log = logging.getLogger(__name__)

_DEFAULT_STATE_FILE = "/tmp/boardfarm-control-sessions.json"


@runtime_checkable
class Launcher(Protocol):
    """Protocol for starting, stopping, and listing agent containers."""

    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,
        runtime_profile: str,
    ) -> AgentInfo:
        """Start a new agent container and return its info.

        :param session_id: unique session identifier
        :type session_id: str
        :param board_name: board this agent will own
        :type board_name: str
        :param image: Docker image to run
        :type image: str
        :param runtime_profile: profile key (stored as label)
        :type runtime_profile: str
        :return: container info
        :rtype: AgentInfo
        """
        ...

    async def stop(self, session_id: str) -> None:
        """Stop and remove the container for a session.

        :param session_id: session whose container to remove
        :type session_id: str
        """
        ...

    async def list_sessions(self) -> list[AgentInfo]:
        """List all running agent sessions.

        :return: info for every running agent container
        :rtype: list[AgentInfo]
        """
        ...


class FakeLauncher:
    """In-memory test double for Launcher. No Docker daemon required."""

    _FIRST_PORT = 18000

    def __init__(self) -> None:
        """Initialise an empty fake launcher."""
        self._sessions: dict[str, AgentInfo] = {}
        self._next_port = self._FIRST_PORT

    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,  # noqa: ARG002
        runtime_profile: str,
    ) -> AgentInfo:
        """Allocate an in-memory session (no Docker).

        :param session_id: unique session identifier
        :type session_id: str
        :param board_name: board this agent will own
        :type board_name: str
        :param image: ignored — no real container
        :type image: str
        :param runtime_profile: profile key
        :type runtime_profile: str
        :return: fake agent info
        :rtype: AgentInfo
        """
        from boardfarm3_control.models import AgentInfo

        port = self._next_port
        self._next_port += 1
        info = AgentInfo(
            session_id=session_id,
            board_name=board_name,
            runtime_profile=runtime_profile,
            container_id=f"fake-{session_id}",
            host_port=port,
            created_at=time.time(),
            pid=None,
            agent_url=f"http://localhost:{port}",
        )
        self._sessions[session_id] = info
        return info

    async def stop(self, session_id: str) -> None:
        """Remove the in-memory session record.

        :param session_id: session to remove
        :type session_id: str
        """
        self._sessions.pop(session_id, None)

    async def list_sessions(self) -> list[AgentInfo]:
        """Return all in-memory session records.

        :return: list of fake agent infos
        :rtype: list[AgentInfo]
        """
        return list(self._sessions.values())


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


class ProcessLauncher:
    """Launcher that starts boardfarm3.api as local subprocesses.

    No Docker daemon required — intended for local development and
    integration testing.
    """

    def __init__(self) -> None:
        """Initialise an empty process launcher."""
        self._sessions: dict[str, tuple[asyncio.subprocess.Process, AgentInfo]] = {}
        self._started = False  # True after first list_sessions() call

    def _state_path(self) -> Path:
        """Return the path of the persistent state file.

        :return: path to the JSON state file
        :rtype: Path
        """
        return Path(
            os.environ.get("BOARDFARM_CONTROL_STATE_FILE", _DEFAULT_STATE_FILE),
        )

    def _save_state(self) -> None:
        """Persist current session state to disk for orphan cleanup on restart.

        :note: Errors are logged but not raised — the state file is best-effort.
        """
        path = self._state_path()
        data = {sid: info.model_dump() for sid, (_, info) in self._sessions.items()}
        tmp = Path(str(path) + ".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            _log.warning("boardfarm control: could not persist state file %s: %s", path, exc)

    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,  # noqa: ARG002
        runtime_profile: str,
    ) -> AgentInfo:
        """Start a boardfarm3.api subprocess on a free local port.

        :param session_id: unique session identifier
        :type session_id: str
        :param board_name: board this agent will own
        :type board_name: str
        :param image: ignored — no container image is used
        :type image: str
        :param runtime_profile: profile key stored in AgentInfo
        :type runtime_profile: str
        :return: agent info with the subprocess pid as container_id
        :rtype: AgentInfo
        """
        from boardfarm3_control.models import AgentInfo

        host_port = _free_port()
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "boardfarm3.api",
            env={
                **os.environ,
                "BOARDFARM_SESSION_ID": session_id,
                "BOARDFARM_BOARD_NAME": board_name,
                "BOARDFARM_AGENT_PORT": str(host_port),
            },
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        info = AgentInfo(
            session_id=session_id,
            board_name=board_name,
            runtime_profile=runtime_profile,
            container_id=str(proc.pid),
            host_port=host_port,
            created_at=time.time(),
            pid=proc.pid,
            agent_url=f"http://localhost:{host_port}",
        )
        self._sessions[session_id] = (proc, info)
        self._save_state()
        return info

    async def stop(self, session_id: str) -> None:
        """Terminate the subprocess for a session.

        Sends SIGTERM and waits up to 5 s; kills if it does not exit.

        :param session_id: session whose subprocess to stop
        :type session_id: str
        """
        entry = self._sessions.pop(session_id, None)
        if entry is None:
            return
        proc, _ = entry
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        self._save_state()

    async def list_sessions(self) -> list[AgentInfo]:
        """Return info for all running agent sessions.

        On the first call, reads the state file and kills any orphaned PIDs
        left by a previous control plane instance.

        :return: list of agent infos
        :rtype: list[AgentInfo]
        """
        if not self._started:
            self._started = True
            await self._cleanup_orphans()
        return [info for _, info in self._sessions.values()]

    async def _cleanup_orphans(self) -> None:
        """Kill any PIDs recorded in the state file from a prior run.

        Reads the state file, sends SIGTERM to each live PID, waits up to
        5 s per PID, then sends SIGKILL if still alive.  Rewrites the state
        file empty afterwards.
        """
        path = self._state_path()
        if not path.exists():
            return
        try:
            data: dict[str, object] = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            _log.warning(
                "boardfarm control: state file corrupt, ignoring: %s",
                path,
            )
            path.unlink(missing_ok=True)
            return

        loop = asyncio.get_running_loop()
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            pid = entry.get("pid")
            if not isinstance(pid, int):
                continue
            try:
                os.kill(pid, 0)  # probe — raises ProcessLookupError if dead
            except (ProcessLookupError, PermissionError):
                continue  # already gone

            # PID is alive — terminate it
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue

            deadline = loop.time() + 5.0
            while loop.time() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                await asyncio.sleep(0.1)
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        # Rewrite state file — all orphans cleaned up, _sessions is empty
        self._save_state()


class DockerLauncher:
    """Production launcher using docker-py (sync calls run in asyncio executor)."""

    _LABEL_SESSION = "boardfarm.session_id"
    _LABEL_BOARD = "boardfarm.board_name"
    _LABEL_PROFILE = "boardfarm.runtime_profile"
    _LABEL_CREATED = "boardfarm.created_at"

    def __init__(self, client: object | None = None) -> None:
        """Initialise with an optional pre-built docker client.

        :param client: docker.DockerClient instance; created from env if None
        :type client: object | None
        """
        import docker as _docker

        self._client = client or _docker.from_env()

    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,
        runtime_profile: str,
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
        :return: agent container info
        :rtype: AgentInfo
        """
        from boardfarm3_control.models import AgentInfo

        host_port = _free_port()
        created_at = time.time()
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
                },
                environment={
                    "BOARDFARM_SESSION_ID": session_id,
                    "BOARDFARM_BOARD_NAME": board_name,
                    "BOARDFARM_AGENT_PORT": "8000",
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
        )

    async def stop(self, session_id: str) -> None:
        """Stop and remove all containers labelled with this session.

        :param session_id: session whose containers to remove
        :type session_id: str
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(
            None,
            lambda: self._client.containers.list(
                filters={"label": f"{self._LABEL_SESSION}={session_id}"},
            ),
        )
        for container in containers:
            await loop.run_in_executor(None, container.stop)
            await loop.run_in_executor(None, container.remove)

    async def list_sessions(self) -> list[AgentInfo]:
        """Return info for every container with a boardfarm.session_id label.

        :return: agent infos rebuilt from Docker container labels
        :rtype: list[AgentInfo]
        """
        from boardfarm3_control.models import AgentInfo

        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(
            None,
            lambda: self._client.containers.list(
                filters={"label": self._LABEL_SESSION},
            ),
        )
        result = []
        for container in containers:
            labels = container.labels
            port_bindings = container.ports.get("8000/tcp") or [{}]
            host_port = int(port_bindings[0].get("HostPort", 0))
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
                ),
            )
        return result
