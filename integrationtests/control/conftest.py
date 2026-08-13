"""Shared fixtures for control-plane integration tests."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, AsyncIterator

import httpx
import pytest

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import ProcessLauncher

if TYPE_CHECKING:
    from boardfarm3_control.models import AgentInfo

_PREWARM_TIMEOUT = 20.0
_PREWARM_INTERVAL = 0.2
_PROFILES = {"local": "unused-image"}

# Minimal boardfarm inventory that parses successfully with no real devices.
# skip_boot=True tells boardfarm_setup_env to return immediately, so the
# session reaches READY state without any device connections being made.
_MINIMAL_SESSION = {
    "board_name": "integration-board",
    "runtime_profile": "local",
    "payload": {
        "inventory": {
            "integration-board": {"devices": []}
        },
        "env": {"environment_def": {}},
    },
    "options": {"skip_boot": True},
}


async def _wait_for_health(host_port: int, timeout: float = _PREWARM_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.get(
                    f"http://localhost:{host_port}/health", timeout=2.0
                )
                if r.status_code == 200:
                    return
            except httpx.TransportError:
                pass
            if time.monotonic() > deadline:
                msg = f"agent on port {host_port} did not become healthy within {timeout}s"
                raise TimeoutError(msg)
            await asyncio.sleep(_PREWARM_INTERVAL)


class _ReadyProcessLauncher(ProcessLauncher):
    """ProcessLauncher that blocks start() until the agent is healthy.

    The control plane's health poll allows only 5 s; this pre-warm ensures
    the agent is already responding by the time start() returns.
    """

    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,
        runtime_profile: str,
    ) -> AgentInfo:
        info = await super().start(session_id, board_name, image, runtime_profile)
        await _wait_for_health(info.host_port)
        return info


@pytest.fixture
async def control_client() -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client for the control plane backed by a ReadyProcessLauncher."""
    launcher = _ReadyProcessLauncher()
    app = create_app(launcher, _PROFILES)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    # Safety net: terminate any subprocess left alive (e.g. test aborted mid-run).
    for info in await launcher.list_sessions():
        await launcher.stop(info.session_id)


@pytest.fixture
async def session(control_client: httpx.AsyncClient) -> AsyncIterator[str]:
    """POST /sessions with a minimal no-device payload; DELETE on teardown."""
    resp = await control_client.post("/sessions", json=_MINIMAL_SESSION)
    assert resp.status_code == 202, resp.text
    sid = resp.json()["session_id"]
    yield sid
    # Best-effort — the test may have already issued DELETE.
    await control_client.delete(f"/sessions/{sid}")
