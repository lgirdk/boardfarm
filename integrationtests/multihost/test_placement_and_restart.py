"""Multi-host scenarios 1-3: placement, per-host registries, control restart."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from integrationtests.multihost.harness import HOST_IPS, agents, body, control

if TYPE_CHECKING:
    from pathlib import Path


async def test_boards_run_on_their_pinned_hosts(
    lab: dict[str, Any], tmp_path: Path
) -> None:
    async with control(lab, tmp_path / "store", "c-it-place") as (client, _app):
        a = await client.post("/sessions", json=body("board-a", "lab-a"))
        b = await client.post("/sessions", json=body("board-b", "lab-b"))
        assert a.status_code == 202, a.text
        assert b.status_code == 202, b.text
        assert a.json()["host"] == "lab-a"
        assert a.json()["agent_url"].startswith(f"http://{HOST_IPS['lab-a']}:")
        assert b.json()["agent_url"].startswith(f"http://{HOST_IPS['lab-b']}:")
        session_a = a.json()["session_id"]
        echo = await client.get(f"/sessions/{session_a}/echo")
        assert echo.json() == {"session": session_a, "board": "board-a"}
        gone = await client.delete(f"/sessions/{session_a}")
        assert gone.json() == {"status": "released"}
        assert agents(lab, "lab-a", "board-a") == []
        assert len(agents(lab, "lab-b", "board-b")) == 1


async def test_per_host_registries_run_the_same_image(
    lab: dict[str, Any], tmp_path: Path
) -> None:
    async with control(lab, tmp_path / "store", "c-it-registry") as (client, _app):
        a = await client.post("/sessions", json=body("board-ra", "lab-a"))
        b = await client.post("/sessions", json=body("board-rb", "lab-b"))
        assert a.status_code == 202, a.text
        assert b.status_code == 202, b.text
        assert a.json()["image_id"] == b.json()["image_id"]


async def test_restart_adopts_sessions_and_keeps_their_leases(
    lab: dict[str, Any], tmp_path: Path
) -> None:
    store = tmp_path / "store"
    async with control(lab, store, "c-it-restart") as (client, _app):
        made = await client.post("/sessions", json=body("board-r", "lab-b"))
        assert made.status_code == 202, made.text
        session_id = made.json()["session_id"]
    async with control(lab, store, "c-it-restart") as (client, _app):
        listing = (await client.get("/sessions")).json()["sessions"]
        assert [(s["session_id"], s["host"], s["state"]) for s in listing] == [
            (session_id, "lab-b", "ready"),
        ]
        again = await client.post("/sessions", json=body("board-r", "lab-b"))
        assert again.status_code == 409
