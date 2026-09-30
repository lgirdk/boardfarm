"""DockerHost: lazy client, per-host pool, timeouts and the circuit breaker."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import docker.errors
import pytest
import requests

from boardfarm3_control.errors import HostUnreachable
from boardfarm3_control.launcher import docker_host
from boardfarm3_control.launcher.docker_host import DockerHost, is_transport_error
from boardfarm3_control.models import HostSpec


class _Client:
    def __init__(self) -> None:
        self.pings = 0

    def ping(self) -> bool:
        self.pings += 1
        return True


def _host(factory: Any = None, **kwargs: Any) -> DockerHost:
    spec = kwargs.pop("spec", HostSpec(docker_url="tcp://10.0.0.5:2375"))
    return DockerHost(
        "lab-1",
        spec,
        client_factory=factory or (lambda _spec, _timeout: _Client()),
        **kwargs,
    )


def test_advertise_addr_defaults_from_docker_url() -> None:
    assert (
        HostSpec(docker_url="tcp://10.0.0.5:2375").effective_advertise_addr()
        == "10.0.0.5"
    )
    assert (
        HostSpec(docker_url="unix:///var/run/docker.sock").effective_advertise_addr()
        == "localhost"
    )
    assert HostSpec().effective_advertise_addr() == "localhost"
    explicit = HostSpec(docker_url="tcp://lab:2375", advertise_addr="10.9.9.9")
    assert explicit.effective_advertise_addr() == "10.9.9.9"


def test_ssh_requires_advertise_addr() -> None:
    with pytest.raises(ValueError, match="advertise_addr"):
        HostSpec(docker_url="ssh://bf@lab3")
    assert (
        HostSpec(docker_url="ssh://bf@lab3", advertise_addr="10.1.1.3").docker_url
        == "ssh://bf@lab3"
    )


def test_tls_is_rejected_until_implemented() -> None:
    with pytest.raises(ValueError, match="NotImplemented"):
        HostSpec(
            docker_url="tcp://lab:2376", tls={"ca": "/ca", "cert": "/c", "key": "/k"}
        )


def test_unknown_scheme_is_rejected() -> None:
    with pytest.raises(ValueError, match="docker_url"):
        HostSpec(docker_url="http://lab:2375")


@pytest.mark.parametrize(
    ("registry", "default", "image", "expected"),
    [
        (None, None, "boardfarm3-agent:1", "boardfarm3-agent:1"),
        (
            None,
            "10.1.1.1:5000",
            "boardfarm3-agent:1",
            "10.1.1.1:5000/boardfarm3-agent:1",
        ),
        ("", "10.1.1.1:5000", "boardfarm3-agent:1", "boardfarm3-agent:1"),
        (
            "mirror.lab:5000",
            "10.1.1.1:5000",
            "agent@sha256:ab",
            "mirror.lab:5000/agent@sha256:ab",
        ),
        ("mirror.lab:5000", None, "lgi/agent:2", "mirror.lab:5000/lgi/agent:2"),
        ("mirror.lab:5000", None, "other.io/agent:2", "other.io/agent:2"),
        ("mirror.lab:5000", None, "localhost/agent:2", "localhost/agent:2"),
        ("mirror.lab:5000", None, "reg:5000/agent:2", "reg:5000/agent:2"),
    ],
)
def test_image_ref(
    registry: str | None, default: str | None, image: str, expected: str
) -> None:
    host = _host(spec=HostSpec(registry=registry), default_registry=default)
    assert host.image_ref(image) == expected
    host.close()


def test_agent_url_uses_advertise_addr() -> None:
    host = _host()
    assert host.agent_url(32768) == "http://10.0.0.5:32768"
    host.close()


def test_api_error_is_not_a_transport_error() -> None:
    assert is_transport_error(requests.exceptions.ConnectionError("refused"))
    assert is_transport_error(TimeoutError())
    assert is_transport_error(docker.errors.DockerException("no version"))
    assert not is_transport_error(docker.errors.NotFound("gone"))
    assert not is_transport_error(docker.errors.APIError("500"))


async def test_client_is_created_lazily_once() -> None:
    made: list[_Client] = []

    def factory(_spec: HostSpec, _timeout: float) -> _Client:
        made.append(_Client())
        return made[-1]

    host = _host(factory)
    assert made == []
    assert await host.ping() is True
    assert await host.ping() is True
    assert len(made) == 1
    host.close()


async def test_transport_failures_trip_the_breaker_and_fail_fast() -> None:
    calls = 0

    def refused(_client: Any) -> None:
        nonlocal calls
        calls += 1
        msg = "refused"
        raise requests.exceptions.ConnectionError(msg)

    host = _host()
    for _ in range(2):
        with pytest.raises(HostUnreachable):
            await host.call(refused)
    assert host.is_down
    assert host.last_error == "refused"
    with pytest.raises(HostUnreachable):
        await host.call(refused)
    assert calls == 2  # the third call never reached the thread pool
    host.close()


async def test_api_error_does_not_trip_breaker() -> None:
    def not_found(_client: Any) -> None:
        msg = "no such container"
        raise docker.errors.NotFound(msg)

    host = _host()
    for _ in range(3):
        with pytest.raises(docker.errors.NotFound):
            await host.call(not_found)
    assert not host.is_down
    assert host.last_ok_at is not None
    host.close()


async def test_client_construction_failure_counts_as_transport() -> None:
    def factory(_spec: HostSpec, _timeout: float) -> _Client:
        msg = "Error while fetching server API version"
        raise docker.errors.DockerException(msg)

    host = _host(factory)
    assert await host.ping() is False
    assert await host.ping() is False
    assert host.is_down
    host.close()


async def test_ping_closes_the_breaker() -> None:
    state = {"fail": True}

    class _Flaky(_Client):
        def ping(self) -> bool:
            if state["fail"]:
                msg = "down"
                raise requests.exceptions.ConnectionError(msg)
            return True

    host = _host(lambda _spec, _timeout: _Flaky())
    assert await host.ping() is False
    assert await host.ping() is False
    assert host.is_down
    state["fail"] = False
    assert await host.ping() is True
    assert not host.is_down
    host.close()


async def test_outer_timeout_counts_as_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(docker_host, "_OUTER_MARGIN", 0.05)
    release = threading.Event()

    def hang(_client: Any) -> None:
        release.wait(5)

    host = _host(timeout=0.1)
    started = time.monotonic()
    with pytest.raises(HostUnreachable):
        await host.call(hang)
    assert time.monotonic() - started < 1.0
    release.set()
    host.close()


async def test_hung_host_does_not_block_another_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(docker_host, "_OUTER_MARGIN", 0.05)
    release = threading.Event()

    def hang(_client: Any) -> None:
        release.wait(5)

    hung = _host(workers=1, timeout=0.2)
    healthy = DockerHost(
        "lab-2",
        HostSpec(docker_url="tcp://10.0.0.6:2375"),
        client_factory=lambda _spec, _timeout: _Client(),
    )
    stuck = [asyncio.create_task(hung.call(hang)) for _ in range(3)]
    await asyncio.sleep(0)
    started = time.monotonic()
    assert await healthy.ping() is True
    assert time.monotonic() - started < 0.5
    results = await asyncio.gather(*stuck, return_exceptions=True)
    assert all(isinstance(result, HostUnreachable) for result in results)
    assert hung.is_down
    release.set()
    hung.close()
    healthy.close()
