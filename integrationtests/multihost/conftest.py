"""Fixtures for the multi-host integration tests; opt in with BOARDFARM_IT_DIND=1."""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import docker
import docker.types
import httpx
import pytest

from integrationtests.multihost.harness import (
    DIND_IMAGE,
    HOST_IPS,
    NETWORK,
    REGISTRY_IMAGE,
    REGISTRY_IP,
    STUB,
    SUBNET,
    docker_url,
    wait_for_daemon,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_STUB_DIR = Path(__file__).parent / "stub_agent"


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip this directory unless BOARDFARM_IT_DIND=1 (it runs privileged containers)."""
    if os.environ.get("BOARDFARM_IT_DIND") == "1":
        return
    skip = pytest.mark.skip(
        reason="set BOARDFARM_IT_DIND=1; needs privileged docker:dind"
    )
    for item in items:
        if "multihost/" in item.nodeid:
            item.add_marker(skip)


def _start_on_network(
    local: docker.DockerClient,
    network: Any,
    image: str,
    name: str,
    ip: str,
    **kwargs: Any,
) -> Any:
    with contextlib.suppress(docker.errors.NotFound):
        local.containers.get(name).remove(force=True, v=True)
    try:
        local.images.get(image)
    except docker.errors.ImageNotFound:
        # containers.create never pulls (containers.run does)
        local.images.pull(image)
    container = local.containers.create(image, name=name, detach=True, **kwargs)
    network.connect(container, ipv4_address=ip)
    container.start()
    return container


def _wait_for_registry(port: str) -> None:
    deadline = time.monotonic() + 30
    while True:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/v2/", timeout=2).status_code == 200:
                return
        except httpx.TransportError:
            pass
        if time.monotonic() > deadline:
            msg = "registry did not come up"
            raise TimeoutError(msg)
        time.sleep(0.5)


@pytest.fixture(scope="session")
def lab() -> Iterator[dict[str, Any]]:
    """Start a registry and two dind lab hosts on a private bridge network with fixed IPs."""
    local = docker.from_env()
    with contextlib.suppress(docker.errors.NotFound):
        local.networks.get(NETWORK).remove()
    network = local.networks.create(
        NETWORK,
        driver="bridge",
        ipam=docker.types.IPAMConfig(
            pool_configs=[docker.types.IPAMPool(subnet=SUBNET)]
        ),
    )
    started: list[Any] = []
    try:
        registry = _start_on_network(
            local,
            network,
            REGISTRY_IMAGE,
            "bf-it-registry",
            REGISTRY_IP,
            ports={"5000/tcp": ("127.0.0.1", None)},
        )
        started.append(registry)
        registry.reload()
        push_port = registry.ports["5000/tcp"][0]["HostPort"]
        _wait_for_registry(push_port)
        local.images.build(path=str(_STUB_DIR), tag=STUB, rm=True)
        pushed = f"127.0.0.1:{push_port}/boardfarm3-agent-stub"
        local.images.get(STUB).tag(pushed, "it")
        local.images.push(pushed, tag="it")
        local.images.remove(f"{pushed}:it")  # the push tag only; STUB stays
        dind: dict[str, Any] = {}
        clients: dict[str, docker.DockerClient] = {}
        for name, ip in HOST_IPS.items():
            dind[name] = _start_on_network(
                local,
                network,
                DIND_IMAGE,
                f"bf-it-{name}",
                ip,
                privileged=True,
                environment={"DOCKER_TLS_CERTDIR": ""},
                command=[
                    "--host=tcp://0.0.0.0:2375",
                    "--tls=false",
                    f"--insecure-registry={REGISTRY_IP}:5000",
                ],
            )
            started.append(dind[name])
            clients[name] = wait_for_daemon(docker_url(name))
        # Preload lab-b the way production hosts get images (a registry pull), under
        # the relative name its registry "" setting resolves to. docker save/load
        # would give another image ID on containerd-store daemons (the Docker 29
        # default), where the ID is the manifest digest, not the config digest.
        pulled = clients["lab-b"].images.pull(
            f"{REGISTRY_IP}:5000/boardfarm3-agent-stub", tag="it"
        )
        pulled.tag("boardfarm3-agent-stub", "it")
        yield {"dind": dind, "clients": clients, "registry": f"{REGISTRY_IP}:5000"}
    finally:
        for container in started:
            with contextlib.suppress(docker.errors.APIError):
                container.remove(force=True, v=True)
        with contextlib.suppress(docker.errors.APIError):
            network.remove()


@pytest.fixture(autouse=True)
def _isolation(
    lab: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[None]:
    """Give each test its own store and a 1 s reconcile loop; afterwards unpause hosts and clear agents."""
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("BOARDFARM_RECONCILE_INTERVAL", "1")
    yield
    for container in lab["dind"].values():
        container.reload()
        if container.status == "paused":
            container.unpause()
    for name in HOST_IPS:
        client = wait_for_daemon(docker_url(name))
        for agent in client.containers.list(
            all=True, filters={"label": "boardfarm.session_id"}
        ):
            agent.remove(force=True)
