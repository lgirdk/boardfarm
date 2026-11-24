"""Keeps the registry, leases and session index in line with each Docker host."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from boardfarm3_control.errors import HostUnreachable, UnknownHost
from boardfarm3_control.teardown import archive_bundle, teardown_session

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx

    from boardfarm3_control.launcher.docker_host import DockerHost
    from boardfarm3_control.launcher.multihost import MultiHostLauncher
    from boardfarm3_control.lease import BoardLease
    from boardfarm3_control.models import AgentInfo
    from boardfarm3_control.registry import SessionRegistry
    from boardfarm3_control.store import DiagnosticsStore

_log = logging.getLogger(__name__)

RECONCILE_INTERVAL_ENV = "BOARDFARM_RECONCILE_INTERVAL"
DEFAULT_RECONCILE_INTERVAL = 30.0


class Reconciler:
    """Applies spec §5.3's table to every reachable host.

    Each daemon is the ground truth for its host. Sessions with a create or a
    teardown in progress (the shared ``inflight`` set) are never touched.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        launcher: MultiHostLauncher,
        registry: SessionRegistry,
        lease: BoardLease,
        store: DiagnosticsStore,
        inflight: set[str],
        http_for: Callable[[AgentInfo], httpx.AsyncClient],
    ) -> None:
        """Wire the reconciler to the control plane's state.

        :param launcher: the multi-host launcher
        :type launcher: MultiHostLauncher
        :param registry: session registry
        :type registry: SessionRegistry
        :param lease: board leases
        :type lease: BoardLease
        :param store: diagnostics store
        :type store: DiagnosticsStore
        :param inflight: session ids with a create or teardown in progress
        :type inflight: set[str]
        :param http_for: returns the HTTP client for a session's agent
        :type http_for: Callable[[AgentInfo], httpx.AsyncClient]
        """
        self._launcher = launcher
        self._registry = registry
        self._lease = lease
        self._store = store
        self._inflight = inflight
        self._http_for = http_for
        self._locks: dict[str, asyncio.Lock] = {}

    async def startup(self) -> None:
        """Restore sessions.json, then reconcile every reachable host.

        Each host costs at most one Docker timeout, so a dead host cannot hang
        startup; its sessions stay as the index recorded them. Pending stops
        are left to the background loop: finishing one can take minutes.
        """
        await self._restore_index()
        await self.reconcile_all(finish_pending=False)

    async def run(self, interval: float) -> None:
        """Reconcile every host every *interval* seconds until cancelled.

        :param interval: seconds between passes
        :type interval: float
        """
        tasks: dict[str, asyncio.Task[None]] = {}
        try:
            while True:
                await asyncio.sleep(interval)
                # One task per host per tick; a host whose previous pass is
                # still running is skipped, so a slow host delays only itself.
                for name in self._launcher.hosts.names():
                    task = tasks.get(name)
                    if task is None or task.done():
                        tasks[name] = asyncio.create_task(self._reconcile_logged(name))
        finally:
            for task in tasks.values():
                task.cancel()

    async def _reconcile_logged(self, name: str) -> None:
        try:
            await self.reconcile_host(name)
        except Exception:  # noqa: BLE001
            _log.exception("reconcile of host %s failed", name)

    async def reconcile_all(self, *, finish_pending: bool = True) -> None:
        """Reconcile every host concurrently; one host's failure never stops the others.

        :param finish_pending: also finish pending stops (the slow row)
        :type finish_pending: bool
        """
        names = self._launcher.hosts.names()
        results = await asyncio.gather(
            *(
                self.reconcile_host(name, finish_pending=finish_pending)
                for name in names
            ),
            return_exceptions=True,
        )
        for name, result in zip(names, results, strict=True):
            if isinstance(result, Exception):
                _log.error("reconcile of host %s failed", name, exc_info=result)

    async def reconcile_host(self, name: str, *, finish_pending: bool = True) -> None:
        """Bring one host's sessions in line with its daemon.

        :param name: host name
        :type name: str
        :param finish_pending: also finish pending stops (the slow row)
        :type finish_pending: bool
        """
        lock = self._locks.setdefault(name, asyncio.Lock())
        if lock.locked():
            return
        async with lock:
            try:
                docker_host = self._launcher.hosts.docker_host(name)
            except UnknownHost:
                return
            # Before the ping: a pending stop must fence its board even while
            # its host is down.
            self._merge_index_pending(name)
            if not await docker_host.ping():
                return
            # Taken before the list: a create or teardown that runs while the
            # list is in flight changes these, and its session is left to the
            # next pass rather than judged on a stale view.
            known = self._host_sessions(name)
            inflight_before = set(self._inflight)
            try:
                observed = await self._launcher.list_host_sessions(name)
            except HostUnreachable:
                return
            seen = {info.session_id: info for info in observed}
            for session_id in sorted(seen.keys() | known.keys()):
                current = self._registry.get(session_id)
                if current is not None and current.host != name:
                    current = None
                if (
                    session_id in inflight_before
                    or session_id in self._inflight
                    or current != known.get(session_id)
                ):
                    continue
                try:
                    await self._reconcile_one(
                        docker_host,
                        seen.get(session_id),
                        current,
                        finish_pending=finish_pending,
                    )
                except Exception:  # noqa: BLE001
                    # One stuck session must not stop the rest of the host's pass.
                    _log.exception(
                        "reconcile of session %s on host %s failed", session_id, name
                    )

    def _merge_index_pending(self, name: str) -> None:
        """Add the host's index-only pending stops to the registry.

        A launch that could not remove its container records a pending stop
        in the index alone; in the registry it fences the board and shows in
        the table.

        :param name: host name
        :type name: str
        """
        for entry in self._launcher.entries(name):
            if (
                entry.info.stop_pending
                and self._registry.get(entry.info.session_id) is None
            ):
                self._registry.add(entry.info)

    def _host_sessions(self, name: str) -> dict[str, AgentInfo]:
        """Return the registry's sessions on host *name*, by id.

        :param name: host name
        :type name: str
        :return: session id to info
        :rtype: dict[str, AgentInfo]
        """
        return {
            info.session_id: info
            for info in self._registry.sessions()
            if info.host == name
        }

    async def _reconcile_one(
        self,
        docker_host: DockerHost,
        seen: AgentInfo | None,
        known: AgentInfo | None,
        *,
        finish_pending: bool = True,
    ) -> None:
        busy = seen is not None and seen.state == "live"
        if known is None or (known.state == "dead" and not known.stop_pending and busy):
            if seen is not None:
                await self._adopt(docker_host, seen)
            return
        if known.stop_pending:
            if seen is None:
                self._drop(known.session_id)
            elif finish_pending:
                await self._finish_teardown(known, seen, busy=busy)
            return
        if known.state != "live":
            return  # a known corpse: the reaper's job
        if seen is None:
            await self._mark_dead(known, ended_at=time.time())
        elif busy:
            self._refresh(known, seen)
        else:
            await self._mark_dead(known, ended_at=seen.ended_at or time.time())

    async def _adopt(self, docker_host: DockerHost, seen: AgentInfo) -> None:
        self._registry.add(seen)
        self._launcher.record(seen)
        if seen.state != "live" or await self._lease.acquire(
            seen.board_name, seen.session_id
        ):
            return
        holder = self._lease.held_by(seen.board_name)
        if holder != seen.session_id:
            docker_host.conflicts += 1
            _log.error(
                "board %s has agents from sessions %s and %s on host %s; "
                "adopted %s without the lease",
                seen.board_name,
                holder,
                seen.session_id,
                docker_host.name,
                seen.session_id,
            )

    def _refresh(self, known: AgentInfo, seen: AgentInfo) -> None:
        updated = known.model_copy(
            update={
                "container_id": seen.container_id,
                "host_port": seen.host_port,
                "agent_url": seen.agent_url,
                "image_id": seen.image_id,
            },
        )
        if updated != known:
            self._registry.add(updated)
            self._launcher.record(updated)

    async def _mark_dead(self, known: AgentInfo, *, ended_at: float) -> None:
        self._registry.mark_dead(known.session_id, ended_at=ended_at)
        await self._lease.release(known.session_id)
        dead = self._registry.get(known.session_id)
        if dead is not None:
            self._launcher.record(dead)

    def _drop(self, session_id: str) -> None:
        self._registry.remove(session_id)
        self._launcher.forget(session_id)

    async def _finish_teardown(
        self, known: AgentInfo, seen: AgentInfo, *, busy: bool
    ) -> None:
        entry = self._launcher.entry(known.session_id)
        retained = entry.retained if entry is not None else False
        http = self._http_for(known)
        self._inflight.add(known.session_id)
        try:
            if busy:
                await teardown_session(
                    session_id=known.session_id,
                    # The daemon's current port, not the recorded one: a
                    # restarted container may have been given a new port.
                    info=known.model_copy(
                        update={
                            "agent_url": seen.agent_url,
                            "host_port": seen.host_port,
                            "container_id": seen.container_id,
                        },
                    ),
                    launcher=self._launcher,
                    registry=self._registry,
                    lease=self._lease,
                    store=self._store,
                    http=http,
                    retain=retained,
                    ended_at=known.ended_at,
                )
                return
            if not self._store.has_bundle(known.session_id):
                await archive_bundle(
                    session_id=known.session_id,
                    # Stopped: its old port may now belong to another board's
                    # agent, so capture from the container only.
                    agent_url="",
                    launcher=self._launcher,
                    store=self._store,
                    http=http,
                    artifact_dir=known.artifact_dir,
                )
            if retained:
                self._registry.mark_dead(
                    known.session_id, ended_at=known.ended_at or time.time()
                )
                done = self._registry.get(known.session_id)
                if done is not None:
                    self._launcher.record(done, retained=True)
            else:
                await self._launcher.purge(known.session_id)
                self._registry.remove(known.session_id)
        finally:
            self._inflight.discard(known.session_id)

    async def _restore_index(self) -> None:
        for entry in self._launcher.entries():
            info = entry.info
            self._registry.add(info)
            if info.state != "live" or info.stop_pending:
                continue
            if not await self._lease.acquire(info.board_name, info.session_id):
                _log.error(
                    "index restore: board %s is already leased to %s; %s restored without the lease",
                    info.board_name,
                    self._lease.held_by(info.board_name),
                    info.session_id,
                )
