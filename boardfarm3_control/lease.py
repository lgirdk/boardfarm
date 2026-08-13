"""Board-exclusive lease management."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3_control.models import AgentInfo


class BoardLease:
    """Asyncio-safe mutual exclusion — one session per board at a time."""

    def __init__(self) -> None:
        """Initialise an empty lease table."""
        self._lock = asyncio.Lock()
        self._leases: dict[str, str] = {}  # board_name -> session_id

    async def acquire(self, board_name: str, session_id: str) -> bool:
        """Attempt to lease a board for a session.

        :param board_name: board to lease
        :type board_name: str
        :param session_id: session requesting the lease
        :type session_id: str
        :return: True if acquired, False if already held
        :rtype: bool
        """
        async with self._lock:
            if board_name in self._leases:
                return False
            self._leases[board_name] = session_id
            return True

    async def release(self, session_id: str) -> None:
        """Release all leases held by a session.

        :param session_id: session whose leases to release
        :type session_id: str
        """
        async with self._lock:
            to_remove = [k for k, v in self._leases.items() if v == session_id]
            for key in to_remove:
                del self._leases[key]

    async def rebuild_from(self, sessions: list[AgentInfo]) -> None:
        """Repopulate the lease table from a list of existing sessions.

        Called on control plane startup so running sessions are not evicted.

        :param sessions: existing sessions recovered from container labels
        :type sessions: list[AgentInfo]
        """
        async with self._lock:
            self._leases = {s.board_name: s.session_id for s in sessions}

    def held_by(self, board_name: str) -> str | None:
        """Return the session currently holding a board, or None.

        :param board_name: board to look up
        :type board_name: str
        :return: session_id or None
        :rtype: str | None
        """
        return self._leases.get(board_name)
