"""Multi-host scenarios 4-8: silent host, reboot, foreign control, race, admin."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import httpx

from boardfarm3_control import teardown
from integrationtests.multihost.harness import (
    DOCKER_TIMEOUT,
    agents,
    body,
    control,
    docker_url,
    eventually,
    wait_for_daemon,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


async def test_silent_host_blocks_only_itself_and_finishes_later(
    lab: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep the paused agent's bundle download short; production reads wait 30 s.
    monkeypatch.setattr(teardown, "_BUNDLE_TIMEOUT", httpx.Timeout(3.0))
    async with control(lab, tmp_path / "store", "c-it-silent") as (client, app):
        made = await client.post("/sessions", json=body("board-s", "lab-b"))
        assert made.status_code == 202, made.text
        session_id = made.json()["session_id"]
        lab["dind"]["lab-b"].pause()  # accepts TCP, never answers
        try:
            started = time.monotonic()
            blocked = await client.post("/sessions", json=body("board-s2", "lab-b"))
            assert blocked.status_code == 503
            assert blocked.json()["detail"]["error"] == "HostUnreachable"
            assert time.monotonic() - started < 2 * (DOCKER_TIMEOUT + 2) + 2
            other = await client.post("/sessions", json=body("board-s3", "lab-a"))
            assert other.status_code == 202, other.text
            gone = await client.delete(f"/sessions/{session_id}")
            assert gone.status_code == 202
            assert gone.json() == {"status": "stop_pending"}
        finally:
            lab["dind"]["lab-b"].unpause()
        await eventually(lambda: agents(lab, "lab-b", "board-s") == [])
        await eventually(lambda: app.state.registry.get(session_id) is None)
        assert app.state.store.has_bundle(session_id)


async def test_restart_while_a_host_is_silent_keeps_its_sessions_and_leases(
    lab: dict[str, Any], tmp_path: Path
) -> None:
    store = tmp_path / "store"
    async with control(lab, store, "c-it-silent-restart") as (client, _app):
        made = await client.post("/sessions", json=body("board-q", "lab-b"))
        assert made.status_code == 202, made.text
        session_id = made.json()["session_id"]
    lab["dind"]["lab-b"].pause()
    try:
        async with control(lab, store, "c-it-silent-restart") as (client, _app):
            listing = (await client.get("/sessions")).json()["sessions"]
            assert [(s["session_id"], s["host"]) for s in listing] == [
                (session_id, "lab-b")
            ]
            # Moving the board to lab-a while lab-b is silent stays blocked.
            moved = await client.post("/sessions", json=body("board-q", "lab-a"))
            assert moved.status_code == 409
    finally:
        lab["dind"]["lab-b"].unpause()


async def test_host_reboot_marks_its_agents_dead_and_frees_the_board(
    lab: dict[str, Any], tmp_path: Path
) -> None:
    async with control(lab, tmp_path / "store", "c-it-reboot") as (client, app):
        made = await client.post("/sessions", json=body("board-h", "lab-b"))
        assert made.status_code == 202, made.text
        session_id = made.json()["session_id"]
        lab["dind"]["lab-b"].restart()
        wait_for_daemon(docker_url("lab-b"))
        await eventually(lambda: app.state.registry.get(session_id).state == "dead")
        again = await client.post("/sessions", json=body("board-h", "lab-b"))
        assert again.status_code == 202, again.text


async def test_a_second_control_plane_never_takes_a_busy_board(
    lab: dict[str, Any], tmp_path: Path
) -> None:
    async with control(lab, tmp_path / "x", "c-it-x") as (x, _app):
        made = await x.post("/sessions", json=body("board-f", "lab-a"))
        assert made.status_code == 202, made.text
        async with control(lab, tmp_path / "y", "c-it-y") as (y, _app):
            refused = await y.post("/sessions", json=body("board-f", "lab-a"))
            assert refused.status_code == 409
            detail = refused.json()["detail"]
            assert (detail["error"], detail["control_id"]) == (
                "BoardBusyOnHost",
                "c-it-x",
            )
            assert (await y.get("/sessions")).json()["sessions"] == []


async def test_racing_control_planes_leave_exactly_one_agent(
    lab: dict[str, Any], tmp_path: Path
) -> None:
    async with (
        control(lab, tmp_path / "x", "c-it-rx") as (x, _x_app),
        control(lab, tmp_path / "y", "c-it-ry") as (y, _y_app),
    ):
        results = await asyncio.gather(
            x.post("/sessions", json=body("board-race", "lab-a")),
            y.post("/sessions", json=body("board-race", "lab-a")),
        )
        assert sorted(result.status_code for result in results) == [202, 409]
        running = [
            c for c in agents(lab, "lab-a", "board-race") if c.status == "running"
        ]
        assert len(running) == 1


async def test_drain_and_forced_host_removal(
    lab: dict[str, Any], tmp_path: Path
) -> None:
    async with control(lab, tmp_path / "store", "c-it-admin") as (client, _app):
        made = await client.post("/sessions", json=body("board-d", "lab-b"))
        assert made.status_code == 202, made.text
        session_id = made.json()["session_id"]
        assert (
            await client.patch("/admin/hosts/lab-a", json={"drain": True})
        ).status_code == 200
        refused = await client.post("/sessions", json=body("board-d2", "lab-a"))
        assert refused.status_code == 503
        assert refused.json()["detail"]["error"] == "HostDraining"
        assert (await client.delete("/admin/hosts/lab-b")).status_code == 409
        forced = await client.delete("/admin/hosts/lab-b?force=true")
        assert forced.json() == {"status": "deleted", "abandoned": [session_id]}
        assert (await client.get("/sessions")).json()["sessions"] == []
