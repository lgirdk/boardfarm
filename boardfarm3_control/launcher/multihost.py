"""Launcher that places each session on its lab host and remembers where."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from boardfarm3_control._jsonfile import read_json, write_json_atomic
from boardfarm3_control.errors import HostUnreachable, NoHostForBoard, StopPending
from boardfarm3_control.launcher.docker import DEFAULT_PULL_TIMEOUT, DockerLauncher
from boardfarm3_control.models import (
    AgentInfo,
)

if TYPE_CHECKING:
    from pathlib import Path

    import httpx

    from boardfarm3_control.hosts import HostRegistry

_log = logging.getLogger(__name__)
_VERSION = 1


class IndexEntry(BaseModel):
    """One session in sessions.json: where it runs and whether to keep its corpse."""

    info: AgentInfo
    retained: bool = False


class MultiHostLauncher:
    """Routes every session to the DockerLauncher of the host it runs on.

    The session→host index is persisted to sessions.json. Each daemon is the
    ground truth for its reachable host; the index fills in for hosts that
    cannot be reached, so a restarted control plane still lists, leases and
    can delete their sessions.
    """

    def __init__(
        self,
        hosts: HostRegistry,
        control_id: str,
        index_path: Path,
        *,
        pull_timeout: float = DEFAULT_PULL_TIMEOUT,
    ) -> None:
        """Load the index; nothing touches the network.

        :param hosts: the host registry
        :type hosts: HostRegistry
        :param control_id: this control plane's id
        :type control_id: str
        :param index_path: sessions.json location
        :type index_path: Path
        :param pull_timeout: seconds allowed for pulling a missing image
        :type pull_timeout: float
        """
        self.hosts = hosts
        self.control_id = control_id
        self._index_path = index_path
        self._pull_timeout = pull_timeout
        self._index = self._load_index()

    def launcher_for(self, host: str) -> DockerLauncher:
        """Return the DockerLauncher for one host.

        :param host: host name
        :type host: str
        :return: a launcher bound to that host and this control plane
        :rtype: DockerLauncher
        """
        return DockerLauncher(
            self.hosts.docker_host(host),
            self.control_id,
            pull_timeout=self._pull_timeout,
        )

    def entry(self, session_id: str) -> IndexEntry | None:
        """Return a session's index entry.

        :param session_id: session to look up
        :type session_id: str
        :return: the entry, or None
        :rtype: IndexEntry | None
        """
        return self._index.get(session_id)

    def entries(self, host: str | None = None) -> list[IndexEntry]:
        """Return every index entry, optionally for one host.

        :param host: host name to filter on
        :type host: str | None
        :return: matching entries
        :rtype: list[IndexEntry]
        """
        return [e for e in self._index.values() if host is None or e.info.host == host]

    def record(self, info: AgentInfo, *, retained: bool | None = None) -> None:
        """Insert or replace a session's entry and save the index.

        :param info: the session's current info
        :type info: AgentInfo
        :param retained: keep the corpse on stop; None keeps the previous value
        :type retained: bool | None
        """
        previous = self._index.get(info.session_id)
        if retained is None:
            retained = previous.retained if previous is not None else False
        self._index[info.session_id] = IndexEntry(info=info, retained=retained)
        self._save_index()

    def forget(self, session_id: str) -> None:
        """Drop a session's entry and save the index.

        :param session_id: session to drop
        :type session_id: str
        """
        if self._index.pop(session_id, None) is not None:
            self._save_index()

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
        """Start the agent on *host* and record where it runs.

        :param session_id: unique session identifier
        :type session_id: str
        :param board_name: board this agent will own
        :type board_name: str
        :param image: profile image
        :type image: str
        :param runtime_profile: profile key
        :type runtime_profile: str
        :param agent_env: extra environment variables for the agent
        :type agent_env: dict[str, str] | None
        :param host: host chosen by placement
        :type host: str | None
        :param mode: the session's mode, recorded so a restarted control plane knows it
        :type mode: str
        :param created_by: identity of the user who triggered this session
        :type created_by: str | None
        :return: the agent's info
        :rtype: AgentInfo
        :raises NoHostForBoard: when no host was chosen
        :raises StopPending: when the launch failed and its container may remain
        :raises OSError: when the session index cannot be saved (the agent is
            removed first)
        """
        if host is None:
            msg = f"no host chosen for board {board_name}"
            raise NoHostForBoard(msg, board_name=board_name)
        try:
            info = await self.launcher_for(host).start(
                session_id,
                board_name,
                image,
                runtime_profile,
                agent_env=agent_env,
                mode=mode,
                created_by=created_by,
            )
        except StopPending as exc:
            # The launch failed and its container could not be removed: record
            # a pending stop so the reconciler removes it once the host answers.
            pending = AgentInfo(
                session_id=session_id,
                board_name=board_name,
                runtime_profile=runtime_profile,
                container_id="",
                host_port=0,
                created_at=time.time(),
                state="dead",
                ended_at=time.time(),
                host=host,
                stop_pending=True,
                mode=mode,
                created_by=created_by,
            )
            self.record(pending, retained=False)
            exc.info = pending
            raise
        try:
            self.record(info, retained=False)
        except OSError:
            await self._remove_unrecorded(info, host)
            raise
        return info

    async def _remove_unrecorded(self, info: AgentInfo, host: str) -> None:
        """Remove the agent of a start whose index entry could not be saved.

        Left running, the next reconcile pass would adopt it as a session
        nobody asked for. Called while handling the save error.

        # noqa: DAR401 error
        # noqa: DAR402 StopPending

        :param info: the started agent's info
        :type info: AgentInfo
        :param host: host it runs on
        :type host: str
        :raises StopPending: when the agent could not be removed either
        """
        _log.exception("could not record %s; removing its agent", info.session_id)
        try:
            await self.launcher_for(host).stop(info.session_id, remove=True)
        except Exception as exc:
            pending = info.model_copy(
                update={"state": "dead", "ended_at": time.time(), "stop_pending": True}
            )
            # Kept in memory only (the index cannot be written): the
            # reconciler still finishes the stop.
            self._index[info.session_id] = IndexEntry(info=pending, retained=False)
            error = StopPending(info.session_id, host)
            error.info = pending
            raise error from exc
        self._index.pop(info.session_id, None)

    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        """Stop a session's agent; record a pending stop when the host cannot confirm it.

        :param session_id: session to stop
        :type session_id: str
        :param remove: also remove the container
        :type remove: bool
        :raises StopPending: when the host could not confirm the stop
        """
        entry = self._index.get(session_id)
        if entry is None or entry.info.host is None:
            return
        dead = entry.info.model_copy(
            update={"state": "dead", "ended_at": entry.info.ended_at or time.time()},
        )
        try:
            await self.launcher_for(entry.info.host).stop(session_id, remove=remove)
        except Exception as exc:
            # A host force-delete may have forgotten the session meanwhile;
            # recording it again would strand its board behind a removed host.
            if session_id in self._index:
                self.record(
                    dead.model_copy(update={"stop_pending": True}), retained=not remove
                )
            raise StopPending(session_id, entry.info.host) from exc
        if remove:
            self.forget(session_id)
        else:
            self.record(dead.model_copy(update={"stop_pending": False}), retained=True)

    async def purge(self, session_id: str) -> None:
        """Force-remove a session's container, then forget it.

        :param session_id: session to purge
        :type session_id: str
        """
        entry = self._index.get(session_id)
        if entry is None or entry.info.host is None:
            return
        await self.launcher_for(entry.info.host).purge(session_id)
        self.forget(session_id)

    async def capture_logs(self, session_id: str) -> bytes:
        """Return the agent's logs from its host.

        :param session_id: session whose logs to capture
        :type session_id: str
        :return: log bytes, empty when unknown or unavailable
        :rtype: bytes
        """
        entry = self._index.get(session_id)
        if entry is None or entry.info.host is None:
            return b""
        return await self.launcher_for(entry.info.host).capture_logs(session_id)

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return a tar of *path* from the agent's container.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: path inside the container
        :type path: str
        :return: tar bytes, empty when unknown or unavailable
        :rtype: bytes
        """
        entry = self._index.get(session_id)
        if entry is None or entry.info.host is None:
            return b""
        return await self.launcher_for(entry.info.host).capture_files(session_id, path)

    async def list_host_sessions(self, host: str) -> list[AgentInfo]:
        """Return this control plane's containers on one host, from its daemon.

        :param host: host name
        :type host: str
        :return: agent infos
        :rtype: list[AgentInfo]
        """
        return await self.launcher_for(host).list_sessions()

    async def list_sessions(self) -> list[AgentInfo]:
        """Return every session: daemons for reachable hosts, the index for the rest.

        :return: agent infos
        :rtype: list[AgentInfo]
        """
        sessions: list[AgentInfo] = []
        for name in self.hosts.names():
            try:
                sessions.extend(await self.list_host_sessions(name))
            except HostUnreachable:  # noqa: PERF203
                sessions.extend(entry.info for entry in self.entries(name))
        return sessions

    def _load_index(self) -> dict[str, IndexEntry]:
        try:
            raw = read_json(self._index_path)
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            _log.warning(
                "session index %s is unreadable; starting empty", self._index_path
            )
            return {}
        sessions = raw.get("sessions", {}) if isinstance(raw, dict) else {}
        entries: dict[str, IndexEntry] = {}
        for session_id, item in sessions.items():
            try:
                entries[session_id] = IndexEntry.model_validate(item)
            except ValidationError:  # noqa: PERF203
                _log.warning("skipping unreadable index entry %s", session_id)
        return entries

    def _save_index(self) -> None:
        sessions = {sid: self._index[sid].model_dump() for sid in sorted(self._index)}
        write_json_atomic(self._index_path, {"version": _VERSION, "sessions": sessions})

    def agent_client(self, info: AgentInfo) -> httpx.AsyncClient | None:  # noqa: ARG002
        """Use the control plane's shared pool for every agent.

        :param info: the session's agent info
        :type info: AgentInfo
        :return: None, meaning the shared pooled client
        :rtype: httpx.AsyncClient | None
        """
        return None
