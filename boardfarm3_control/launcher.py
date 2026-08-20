"""Container lifecycle management for boardfarm agent sessions."""

from __future__ import annotations

import asyncio
import functools
import io
import json
import logging
import os
import signal
import socket
import sys
import tarfile
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Protocol, runtime_checkable

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
        agent_env: dict[str, str] | None = None,
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
        :param agent_env: extra environment variables to pass to the agent
        :type agent_env: dict[str, str] | None
        :return: container info
        :rtype: AgentInfo
        """
        ...

    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        """Stop the container, and remove it only when *remove* is set.

        :param session_id: session whose container to stop
        :type session_id: str
        :param remove: also remove the container, as ``docker rm`` would
        :type remove: bool
        """
        ...

    async def purge(self, session_id: str) -> None:
        """Remove a stopped session's record entirely.

        :param session_id: session to purge
        :type session_id: str
        """
        ...

    async def capture_logs(self, session_id: str) -> bytes:
        """Return the captured stdout/stderr for a session.

        :param session_id: session whose output to capture
        :type session_id: str
        :return: log bytes, empty when unavailable
        :rtype: bytes
        """
        ...

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return a tar archive of *path* for a session.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: path to archive
        :type path: str
        :return: tar bytes, empty when unavailable
        :rtype: bytes
        """
        ...

    async def list_sessions(self) -> list[AgentInfo]:
        """List all agent sessions.

        :return: info for every known agent container, running or stopped
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
        agent_env: dict[str, str] | None = None,  # noqa: ARG002
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

    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        """Mark a session dead, optionally dropping its record.

        :param session_id: session to stop
        :type session_id: str
        :param remove: also forget the session, as ``docker rm`` would
        :type remove: bool
        """
        if remove:
            self._sessions.pop(session_id, None)
            return
        info = self._sessions.get(session_id)
        if info is not None:
            self._sessions[session_id] = info.model_copy(
                update={"state": "dead", "ended_at": time.time()},
            )

    async def purge(self, session_id: str) -> None:
        """Forget a stopped session.

        :param session_id: session to purge
        :type session_id: str
        """
        self._sessions.pop(session_id, None)

    async def capture_logs(self, session_id: str) -> bytes:
        """Return synthetic agent output for tests.

        :param session_id: session whose output to capture
        :type session_id: str
        :return: log bytes, empty when the session is unknown
        :rtype: bytes
        """
        if session_id not in self._sessions:
            return b""
        return f"fake logs for {session_id}\n".encode()

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return synthetic tar bytes for tests.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: path inside the agent
        :type path: str
        :return: tar bytes, empty when the session is unknown
        :rtype: bytes
        """
        if session_id not in self._sessions:
            return b""
        return f"fake tar of {path} for {session_id}".encode()

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
        self._sessions: dict[
            str,
            tuple[asyncio.subprocess.Process, AgentInfo, IO[bytes]],
        ] = {}
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
        data = {
            sid: info.model_dump()
            for sid, (_, info, _log_file) in self._sessions.items()
        }
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
        agent_env: dict[str, str] | None = None,
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
        :param agent_env: extra environment variables for the subprocess
        :type agent_env: dict[str, str] | None
        :return: agent info with the subprocess pid as container_id
        :rtype: AgentInfo
        """
        from boardfarm3_control.models import AgentInfo

        host_port = _free_port()
        log_dir = (
            Path(
                os.environ.get(
                    "BOARDFARM_CONTROL_STORE",
                    "/var/lib/boardfarm-control",
                ),
            )
            / "sessions"
            / session_id
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = (log_dir / "process.log").open("wb")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "boardfarm3.api",
            env={
                **os.environ,
                "BOARDFARM_SESSION_ID": session_id,
                "BOARDFARM_BOARD_NAME": board_name,
                "BOARDFARM_AGENT_PORT": str(host_port),
                **(agent_env or {}),
            },
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
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
        self._sessions[session_id] = (proc, info, log_file)
        self._save_state()
        return info

    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        """Terminate the subprocess for a session.

        Sends SIGTERM and waits up to 5 s; kills if it does not exit.

        :param session_id: session whose subprocess to stop
        :type session_id: str
        :param remove: also forget the session record
        :type remove: bool
        """
        entry = (
            self._sessions.pop(session_id, None)
            if remove
            else self._sessions.get(session_id)
        )
        if entry is None:
            return
        proc, _info, log_file = entry
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        log_file.close()
        self._save_state()

    async def purge(self, session_id: str) -> None:
        """Delete the on-disk record for a stopped session.

        :param session_id: session to purge
        :type session_id: str
        """
        self._sessions.pop(session_id, None)
        self._save_state()

    async def capture_logs(self, session_id: str) -> bytes:
        """Read the subprocess output file for a session.

        :param session_id: session whose output to read
        :type session_id: str
        :return: log bytes, empty when unavailable
        :rtype: bytes
        """
        path = (
            Path(
                os.environ.get(
                    "BOARDFARM_CONTROL_STORE",
                    "/var/lib/boardfarm-control",
                ),
            )
            / "sessions"
            / session_id
            / "process.log"
        )
        try:
            return path.read_bytes()
        except OSError:
            return b""

    async def capture_files(self, session_id: str, path: str) -> bytes:  # noqa: ARG002
        """Return a tar of *path*, which is local for this launcher.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: local path to archive
        :type path: str
        :return: tar bytes, empty when the path does not exist
        :rtype: bytes
        """
        source = Path(path)
        if not source.exists():
            return b""
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            archive.add(source, arcname=source.name)
        return buffer.getvalue()

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
        return [info for _, info, _log_file in self._sessions.values()]

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
        from boardfarm3_control.models import AgentInfo

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
                ),
            )
        return result
