"""Launcher that runs boardfarm3.api as local subprocesses."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import signal
import sys
import tarfile
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING

from boardfarm3_control.launcher._common import _artifact_root, _free_port

if TYPE_CHECKING:
    import httpx

    from boardfarm3_control.models import AgentInfo

_log = logging.getLogger(__name__)

_DEFAULT_STATE_FILE = "/tmp/boardfarm-control-sessions.json"  # noqa: S108


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
            tmp.replace(path)
        except OSError as exc:
            _log.warning(
                "boardfarm control: could not persist state file %s: %s", path, exc
            )

    async def start(  # noqa: PLR0913
        self,
        session_id: str,
        board_name: str,
        image: str,  # noqa: ARG002
        runtime_profile: str,
        agent_env: dict[str, str] | None = None,
        host: str | None = None,  # noqa: ARG002
        mode: str = "interact",
        created_by: str | None = None,
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
        :param host: lab host to place the agent on; ignored by single-host launchers
        :type host: str | None
        :param mode: the session's mode, recorded so a restarted control plane knows it
        :type mode: str
        :param created_by: identity of the user who triggered this session
        :type created_by: str | None
        :return: agent info with the subprocess pid as container_id
        :rtype: AgentInfo
        """
        from boardfarm3_control.models import AgentInfo  # noqa: PLC0415

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
        # Written alongside process.log so the reaper's aged-bundle sweep
        # never mistakes a live session's freshly created store directory
        # for an ended one: no "ended_at" key means "not eligible" (see
        # reaper._reap_aged_bundles), not "infinitely old".
        try:
            (log_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "board_name": board_name,
                        "runtime_profile": runtime_profile,
                        "created_at": time.time(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            _log.warning(
                "boardfarm control: could not write meta.json in %s: %s",
                log_dir,
                exc,
            )
        log_file = (log_dir / "process.log").open("wb")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "boardfarm3.api",
            # Identity last: agent_env may add variables, never re-point the agent.
            env={
                **os.environ,
                **(agent_env or {}),
                "BOARDFARM_SESSION_ID": session_id,
                "BOARDFARM_BOARD_NAME": board_name,
                "BOARDFARM_AGENT_PORT": str(host_port),
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
            artifact_dir=_artifact_root(agent_env),
            mode=mode,
            created_by=created_by,
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
        proc, info, log_file = entry
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        log_file.close()
        if not remove:
            self._sessions[session_id] = (
                proc,
                info.model_copy(update={"state": "dead", "ended_at": time.time()}),
                log_file,
            )
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

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return a tar of *path*, which is local for this launcher.

        Refuses anything whose final path component is not *session_id*: the
        caller is expected to pass this session's own artifact directory
        (``{artifact_root}/{session_id}``), and this launcher shares its
        filesystem with the control plane, so a caller-supplied path that
        strayed into another session's directory would otherwise leak one
        session's console transcripts into another's bundle.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: local path to archive; must end in ``/{session_id}``
        :type path: str
        :return: tar bytes, empty when the path does not exist or is not
            scoped to this session
        :rtype: bytes
        """
        source = Path(path)
        if source.name != session_id:
            _log.warning(
                "capture_files for %s refused non-session path %s",
                session_id,
                path,
            )
            return b""
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

        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            pid = entry.get("pid")
            if not isinstance(pid, int):
                continue
            # After a reboot the PID may belong to anything: only kill a
            # process that carries the recorded session in its environment.
            if not self._is_agent(pid, str(entry.get("session_id", ""))):
                continue
            await self._terminate_pid(pid)

        # Rewrite state file — all orphans cleaned up, _sessions is empty
        self._save_state()

    @staticmethod
    def _is_agent(pid: int, session_id: str) -> bool:
        """Report whether *pid* is the agent this launcher started for *session_id*.

        :param pid: recorded process id
        :type pid: int
        :param session_id: session recorded with it
        :type session_id: str
        :return: True only when the process environment names that session
        :rtype: bool
        """
        if not session_id:
            return False
        try:
            environ = Path(f"/proc/{pid}/environ").read_bytes()
        except OSError:  # gone, not ours to read, or no /proc
            return False
        return f"BOARDFARM_SESSION_ID={session_id}".encode() in environ.split(b"\0")

    @staticmethod
    async def _terminate_pid(pid: int) -> None:
        """Send SIGTERM to a live PID, wait up to 5 s, then SIGKILL it.

        :param pid: process id to terminate
        """
        loop = asyncio.get_running_loop()
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        deadline = loop.time() + 5.0
        while loop.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            await asyncio.sleep(0.1)
        else:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)

    def agent_client(self, info: AgentInfo) -> httpx.AsyncClient | None:  # noqa: ARG002
        """Use the control plane's shared pool for every agent.

        :param info: the session's agent info
        :type info: AgentInfo
        :return: None, meaning the shared pooled client
        :rtype: httpx.AsyncClient | None
        """
        return None
