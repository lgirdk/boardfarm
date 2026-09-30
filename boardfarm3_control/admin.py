"""Runtime management of lab hosts under /admin (gate it at the reverse proxy)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from boardfarm3_control.errors import HostInUse
from boardfarm3_control.models import HostPatch, HostSpec, HostStatus, HostView

if TYPE_CHECKING:
    from boardfarm3_control.launcher.multihost import MultiHostLauncher
    from boardfarm3_control.lease import BoardLease
    from boardfarm3_control.registry import SessionRegistry


def build_admin_router(  # noqa: C901
    *,
    launcher: MultiHostLauncher,
    registry: SessionRegistry,
    lease: BoardLease,
) -> APIRouter:
    """Build the ``/admin/hosts`` routes.

    :param launcher: the multi-host launcher whose hosts are managed
    :type launcher: MultiHostLauncher
    :param registry: session registry, to count and abandon sessions
    :type registry: SessionRegistry
    :param lease: board leases, released when sessions are abandoned
    :type lease: BoardLease
    :return: the admin router
    :rtype: APIRouter
    """
    hosts = launcher.hosts
    router = APIRouter(prefix="/admin", tags=["admin"])

    def _counts(name: str) -> dict[str, int]:
        counts = {"live": 0, "dead": 0, "stop_pending": 0}
        for info in registry.sessions():
            if info.host != name:
                continue
            if info.stop_pending:
                counts["stop_pending"] += 1
            elif info.state == "dead":
                counts["dead"] += 1
            else:
                counts["live"] += 1
        return counts

    def _sessions_on(name: str) -> list[str]:
        # The index as well as the registry: a failed launch's pending stop
        # may be known only to sessions.json.
        in_registry = {
            info.session_id for info in registry.sessions() if info.host == name
        }
        in_index = {entry.info.session_id for entry in launcher.entries(name)}
        return sorted(in_registry | in_index)

    def _in_use(name: str) -> bool:
        return bool(_sessions_on(name))

    def _known(name: str) -> None:
        if name not in hosts.names():
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown host {name}",
            )

    def _view(name: str, probe: bool | None = None) -> HostView:
        docker_host = hosts.docker_host(name)
        return HostView(
            name=name,
            spec=docker_host.spec,
            effective_registry=docker_host.effective_registry,
            status=HostStatus(
                breaker="down" if docker_host.is_down else "up",
                last_error=docker_host.last_error,
                last_ok_at=docker_host.last_ok_at,
                sessions=_counts(name),
                conflicts=docker_host.conflicts,
            ),
            probe=probe,
        )

    @router.get("/hosts")
    async def list_hosts() -> list[HostView]:
        return [_view(name) for name in hosts.names()]

    @router.get("/hosts/{name}")
    async def get_host(name: str) -> HostView:
        _known(name)
        return _view(name)

    @router.put("/hosts/{name}")
    async def put_host(name: str, spec: HostSpec) -> HostView:
        try:
            await hosts.put(name, spec, in_use=_in_use(name))
        except ValueError as exc:
            raise HTTPException(
                status_code=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                detail=str(exc),
            ) from exc
        probe = await hosts.docker_host(name).ping()
        return _view(name, probe=probe)

    @router.patch("/hosts/{name}")
    async def patch_host(name: str, patch: HostPatch) -> HostView:
        _known(name)
        changes = patch.model_dump(include=patch.model_fields_set)
        try:
            await hosts.patch(name, changes, in_use=_in_use(name))
        except ValueError as exc:
            raise HTTPException(
                status_code=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                detail=str(exc),
            ) from exc
        return _view(name)

    @router.delete("/hosts/{name}")
    async def delete_host(name: str, force: bool = False) -> dict[str, object]:
        _known(name)
        abandoned = _sessions_on(name)
        if abandoned and not force:
            msg = f"host {name} has {len(abandoned)} session(s); delete them, or pass force=true"
            raise HostInUse(msg, host=name, sessions=abandoned)
        # force: the operator accepts that this host's agents may still run.
        for session_id in abandoned:
            registry.remove(session_id)
            await lease.release(session_id)
            launcher.forget(session_id)
        await hosts.delete(name, in_use=False)
        return {"status": "deleted", "abandoned": abandoned}

    return router
