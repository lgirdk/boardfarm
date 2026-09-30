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

    def mark_dead(
        self, session_id: str, ended_at: float, *, stop_pending: bool = False
    ) -> None:
        """Mark a session dead while keeping it listed.

        A corpse stays in the registry so it can be found, its diagnostics
        served, and its container purged. ``AgentInfo`` is frozen, so the
        entry is replaced rather than mutated.

        :param session_id: session to mark
        :type session_id: str
        :param ended_at: when the session ended
        :type ended_at: float
        :param stop_pending: the host could not confirm the stop yet
        :type stop_pending: bool
        """
        info = self._sessions.get(session_id)
        if info is None:
            return
        self._sessions[session_id] = info.model_copy(
            update={
                "state": "dead",
                "ended_at": ended_at,
                "stop_pending": stop_pending,
            },
        )

    async def rebuild(self, launcher: Launcher) -> None:
        """Repopulate the registry from launcher-listed sessions.

        Called on startup to recover state after a control plane restart.

        :param launcher: launcher whose list_sessions() enumerates running agents
        :type launcher: Launcher
        """
        sessions = await launcher.list_sessions()
        self._sessions = {s.session_id: s for s in sessions}
        self._last_activity = {}

    def sessions(self) -> list[AgentInfo]:
        """Return every registered session.

        :return: all sessions
        :rtype: list[AgentInfo]
        """
        return list(self._sessions.values())

    def pending_stop_for(self, board_name: str) -> AgentInfo | None:
        """Return a session of *board_name* whose stop is not confirmed yet.

        :param board_name: board to look up
        :type board_name: str
        :return: the pending session, or None
        :rtype: AgentInfo | None
        """
        return next(
            (
                info
                for info in self._sessions.values()
                if info.board_name == board_name and info.stop_pending
            ),
            None,
        )
