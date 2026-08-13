"""In-memory session registry rebuilt from Docker container labels on restart."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.models import AgentInfo


class SessionRegistry:
    """In-memory store of active sessions; rebuilt from the launcher on startup."""

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._sessions: dict[str, AgentInfo] = {}
        self._last_activity: dict[str, float] = {}

    def add(self, info: AgentInfo) -> None:
        """Register a new session.

        :param info: agent info to store
        :type info: AgentInfo
        """
        self._sessions[info.session_id] = info

    def remove(self, session_id: str) -> None:
        """Remove a session from the registry.

        :param session_id: session to remove
        :type session_id: str
        """
        self._sessions.pop(session_id, None)
        self._last_activity.pop(session_id, None)

    def get(self, session_id: str) -> AgentInfo | None:
        """Look up a session by ID.

        :param session_id: session to look up
        :type session_id: str
        :return: agent info, or None if unknown
        :rtype: AgentInfo | None
        """
        return self._sessions.get(session_id)

    def list_page(self, offset: int, limit: int) -> tuple[list[AgentInfo], int]:
        """Return a paginated slice of all sessions and the total count.

        :param offset: number of sessions to skip
        :type offset: int
        :param limit: maximum sessions to return
        :type limit: int
        :return: (page, total)
        :rtype: tuple[list[AgentInfo], int]
        """
        all_sessions = list(self._sessions.values())
        total = len(all_sessions)
        return all_sessions[offset : offset + limit], total

    def agent_url(self, session_id: str) -> str | None:
        """Return the base URL for the agent serving this session.

        :param session_id: session to look up
        :type session_id: str
        :return: ``http://localhost:{port}`` or None if unknown
        :rtype: str | None
        """
        info = self._sessions.get(session_id)
        if info is None:
            return None
        return f"http://localhost:{info.host_port}"

    def touch(self, session_id: str) -> None:
        """Record current time as last_activity for a session.

        :param session_id: session to touch
        :type session_id: str
        """
        self._last_activity[session_id] = time.time()

    def last_activity(self, session_id: str) -> float | None:
        """Return the last-activity timestamp for a session, or None.

        :param session_id: session to query
        :type session_id: str
        :return: UNIX timestamp or None
        :rtype: float | None
        """
        return self._last_activity.get(session_id)

    async def rebuild(self, launcher: Launcher) -> None:
        """Repopulate the registry from launcher-listed sessions.

        Called on startup to recover state after a control plane restart.

        :param launcher: launcher whose list_sessions() enumerates running agents
        :type launcher: Launcher
        """
        sessions = await launcher.list_sessions()
        self._sessions = {s.session_id: s for s in sessions}
        self._last_activity = {}
