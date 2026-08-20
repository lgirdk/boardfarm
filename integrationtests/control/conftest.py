"""Shared fixtures for control-plane integration tests."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, AsyncIterator

import httpx
import pytest
import uvicorn

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
        "inventory": {"integration-board": {"devices": []}},
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
        agent_env: dict[str, str] | None = None,
    ) -> AgentInfo:
        info = await super().start(
            session_id,
            board_name,
            image,
            runtime_profile,
            agent_env,
        )
        await _wait_for_health(info.host_port)
        return info


@pytest.fixture(autouse=True)
def _isolated_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Keep integration artifacts out of /var, which is not writable in CI.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path_factory: pytest temp directory factory
    :type tmp_path_factory: pytest.TempPathFactory
    """
    root = tmp_path_factory.mktemp("bf-integration")
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(root / "control"))
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(root / "artifacts"))
    # Keep the SSE keepalive test from waiting the 15 s production default.
    monkeypatch.setenv("BOARDFARM_SSE_KEEPALIVE", "1")


@pytest.fixture
async def control_client() -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client for the control plane backed by a ReadyProcessLauncher."""
    launcher = _ReadyProcessLauncher()
    app = create_app(launcher, _PROFILES)
    transport = httpx.ASGITransport(app=app)
    # httpx.ASGITransport never sends lifespan events, so app.state.http
    # (created only in create_app's lifespan) would otherwise never exist —
    # run the lifespan explicitly, the way a real ASGI server would.
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield client
        # Safety net: terminate any subprocess left alive (e.g. test aborted
        # mid-run).
        for info in await launcher.list_sessions():
            await launcher.stop(info.session_id)


@pytest.fixture
async def control_server() -> AsyncIterator[str]:
    """Run the control plane under uvicorn on a real socket; yield its base URL.

    ``httpx.ASGITransport`` (used by ``control_client``) drains an ASGI
    app's *entire* response before it ever returns control to the caller —
    see ``handle_async_request`` in httpx's ``asgi.py``, which awaits
    ``self.app(...)`` to completion and only then hands back a ``Response``.
    That makes it structurally unable to host an unbounded stream: the
    console SSE generator only stops on client disconnect, and disconnect
    is only observed by awaiting a further ``receive()`` call that itself
    blocks on the very completion the generator is waiting to be told about
    — a deadlock. A real socket, exactly what a production ``uvicorn.run()``
    deployment already uses, has no such restriction.
    """
    launcher = _ReadyProcessLauncher()
    app = create_app(launcher, _PROFILES)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        # Safety net: terminate any subprocess left alive (e.g. test aborted
        # mid-run).
        for info in await launcher.list_sessions():
            await launcher.stop(info.session_id)
        server.should_exit = True
        await serve_task


@pytest.fixture
async def session(control_client: httpx.AsyncClient) -> AsyncIterator[str]:
    """POST /sessions with a minimal no-device payload; DELETE on teardown."""
    resp = await control_client.post("/sessions", json=_MINIMAL_SESSION)
    assert resp.status_code == 202, resp.text
    sid = resp.json()["session_id"]
    yield sid
    # Best-effort — the test may have already issued DELETE.
    await control_client.delete(f"/sessions/{sid}")
