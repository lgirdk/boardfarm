"""The protocol every agent launcher implements."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import httpx

    from boardfarm3_control.models import AgentInfo


@runtime_checkable
class Launcher(Protocol):
    """Protocol for starting, stopping, and listing agent containers."""

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
        :param host: lab host to place the agent on; ignored by single-host launchers
        :type host: str | None
        :param mode: the session's mode, recorded so a restarted control plane knows it
        :type mode: str
        :param created_by: identity of the user who triggered this session
        :type created_by: str | None
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

    def agent_client(self, info: AgentInfo) -> httpx.AsyncClient | None:
        """Return the HTTP client for reaching *info*'s agent.

        :param info: the session's agent info
        :type info: AgentInfo
        :return: a client, or None to use the control plane's shared pool
        :rtype: httpx.AsyncClient | None
        """
        ...
