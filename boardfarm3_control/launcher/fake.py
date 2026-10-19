"""In-memory launcher for tests; no Docker daemon required."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from boardfarm3_control.launcher._common import _artifact_root

if TYPE_CHECKING:
    import httpx

    from boardfarm3_control.models import AgentInfo


class FakeLauncher:
    """In-memory test double for Launcher. No Docker daemon required."""

    _FIRST_PORT = 18000

    def __init__(self) -> None:
        """Initialise an empty fake launcher."""
        self._sessions: dict[str, AgentInfo] = {}
        self._next_port = self._FIRST_PORT

    async def start(  # noqa: PLR0913
        self,
        session_id: str,
        board_name: str,
        image: str,  # noqa: ARG002
        runtime_profile: str,
        agent_env: dict[str, str] | None = None,
        host: str | None = None,  # noqa: ARG002
        mode: str = "interact",
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
        :param agent_env: extra environment variables, honoured only for
            ``BOARDFARM_ARTIFACT_DIR``
        :type agent_env: dict[str, str] | None
        :param host: lab host to place the agent on; ignored by single-host launchers
        :type host: str | None
        :param mode: the session's mode, recorded so a restarted control plane knows it
        :type mode: str
        :return: fake agent info
        :rtype: AgentInfo
        """
        from boardfarm3_control.models import AgentInfo  # noqa: PLC0415

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
            artifact_dir=_artifact_root(agent_env),
            mode=mode,
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

    def agent_client(self, info: AgentInfo) -> httpx.AsyncClient | None:  # noqa: ARG002
        """Use the control plane's shared pool for every agent.

        :param info: the session's agent info
        :type info: AgentInfo
        :return: None, meaning the shared pooled client
        :rtype: httpx.AsyncClient | None
        """
        return None
