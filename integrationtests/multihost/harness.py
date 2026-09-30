"""Helpers for the multi-host integration tests (two docker:dind lab hosts)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from typing import TYPE_CHECKING, Any

import docker
import httpx

from boardfarm3_control.app import create_app
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher import MultiHostLauncher
from boardfarm3_control.launcher.docker_host import DockerHost

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

    from fastapi import FastAPI

SUBNET = os.environ.get("BF_IT_SUBNET", "172.31.250.0/24")
_PREFIX = SUBNET.rsplit(".", 1)[0]
REGISTRY_IP = f"{_PREFIX}.10"
HOST_IPS = {"lab-a": f"{_PREFIX}.11", "lab-b": f"{_PREFIX}.12"}
DIND_IMAGE = os.environ.get("BF_IT_DIND_IMAGE", "docker:29.1.4-alpine3.23")
REGISTRY_IMAGE = os.environ.get("BF_IT_REGISTRY_IMAGE", "registry:2")
NETWORK = "bf-it-multihost"
STUB = "boardfarm3-agent-stub:it"
DOCKER_TIMEOUT = 3.0


def docker_url(host: str) -> str:
    return f"tcp://{HOST_IPS[host]}:2375"


def wait_for_daemon(url: str, deadline_s: float = 90.0) -> docker.DockerClient:
    deadline = time.monotonic() + deadline_s
    while True:
        try:
            client = docker.DockerClient(base_url=url, timeout=5)
            client.ping()
        except docker.errors.DockerException:  # noqa: PERF203
            if time.monotonic() > deadline:
                raise
            time.sleep(1)
        else:
            return client


def body(board: str, host: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"devices": []}
    if host is not None:
        entry["agent_host"] = host
    return {
        "board_name": board,
        "runtime_profile": "stub",
        "payload": {"inventory": {board: entry}, "env": {"environment_def": {}}},
    }


def agents(lab: dict[str, Any], host: str, board: str) -> list[Any]:
    return lab["clients"][host].containers.list(
        all=True,
        filters={"label": f"boardfarm.board_name={board}"},
    )


async def eventually(check: Callable[[], bool], timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            msg = "condition not met in time"
            raise AssertionError(msg)
        await asyncio.sleep(0.5)


@contextlib.asynccontextmanager
async def control(
    lab: dict[str, Any],
    store: Path,
    control_id: str,
) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    """Run one control plane over both lab hosts; lab-a pulls from the registry, lab-b uses its preloaded image."""
    seed = {
        "lab-a": {
            "docker_url": docker_url("lab-a"),
            "registry": lab["registry"],
            "default": True,
        },
        "lab-b": {"docker_url": docker_url("lab-b"), "registry": ""},
    }
    hosts = HostRegistry.load(
        store / "hosts.json",
        seed=seed,
        host_factory=lambda name, spec: DockerHost(name, spec, timeout=DOCKER_TIMEOUT),
    )
    launcher = MultiHostLauncher(
        hosts, control_id, store / "sessions.json", pull_timeout=120.0
    )
    app = create_app(launcher, {"stub": STUB})
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://control",
                timeout=120.0,
            ) as client,
        ):
            yield client, app
    finally:
        hosts.close()
