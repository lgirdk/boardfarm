"""resolve_host: inventory agent_host first, then the default host."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from boardfarm3_control.errors import NoHostForBoard, UnknownHost
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.placement import resolve_host

if TYPE_CHECKING:
    from pathlib import Path


def _hosts(tmp_path: Path, fake_daemon: Any, seed: dict[str, Any]) -> HostRegistry:
    daemon = fake_daemon()
    return HostRegistry.load(
        tmp_path / "hosts.json",
        seed=seed,
        host_factory=lambda name, spec: DockerHost(
            name, spec, client_factory=daemon.client_factory
        ),
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"inventory": {"b1": {"devices": [], "agent_host": "lab-2"}}}, "lab-2"),
        ({"inventory": {"b1": {"devices": []}}}, "lab-1"),
        ({"inventory": {}}, "lab-1"),
        ({}, "lab-1"),
    ],
)
def test_resolve_host(
    tmp_path: Path, fake_daemon: Any, payload: dict[str, Any], expected: str
) -> None:
    hosts = _hosts(tmp_path, fake_daemon, {"lab-1": {"default": True}, "lab-2": {}})
    assert resolve_host(payload, "b1", hosts) == expected
    hosts.close()


def test_no_agent_host_and_no_default_is_no_host_for_board(
    tmp_path: Path, fake_daemon: Any
) -> None:
    hosts = _hosts(tmp_path, fake_daemon, {"lab-1": {}})
    with pytest.raises(NoHostForBoard):
        resolve_host({"inventory": {"b1": {"devices": []}}}, "b1", hosts)
    hosts.close()


@pytest.mark.parametrize("value", ["lab-9", 42, ["lab-1"]])
def test_unknown_or_non_string_agent_host(
    tmp_path: Path, fake_daemon: Any, value: object
) -> None:
    hosts = _hosts(tmp_path, fake_daemon, {"lab-1": {"default": True}})
    with pytest.raises(UnknownHost):
        resolve_host({"inventory": {"b1": {"agent_host": value}}}, "b1", hosts)
    hosts.close()
