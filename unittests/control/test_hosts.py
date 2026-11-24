"""HostRegistry: hosts.json, first-boot seeding, the default host and in-use rules."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import pytest

from boardfarm3_control.errors import HostInUse, UnknownHost
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.models import HostSpec

if TYPE_CHECKING:
    from pathlib import Path


def _load(path: Path, fake_daemon: Any, seed: dict[str, Any] | None) -> HostRegistry:
    daemon = fake_daemon()
    return HostRegistry.load(
        path,
        seed=seed,
        host_factory=lambda name, spec: DockerHost(
            name, spec, client_factory=daemon.client_factory
        ),
    )


def test_first_boot_without_seed_creates_the_implicit_local_host(
    tmp_path: Path, fake_daemon: Any
) -> None:
    hosts = _load(tmp_path / "hosts.json", fake_daemon, None)
    assert hosts.names() == ["local"]
    assert hosts.default_host() == "local"
    assert hosts.docker_host("local").advertise_addr == "localhost"
    saved = json.loads((tmp_path / "hosts.json").read_text())
    assert saved["version"] == 1
    assert saved["hosts"]["local"]["registry"] == ""
    hosts.close()


def test_seed_is_read_only_on_first_boot(
    tmp_path: Path, fake_daemon: Any, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "hosts.json"
    _load(path, fake_daemon, {"lab-1": {"docker_url": "tcp://10.0.0.5:2375"}}).close()
    with caplog.at_level(logging.WARNING):
        hosts = _load(
            path, fake_daemon, {"lab-2": {"docker_url": "tcp://10.0.0.6:2375"}}
        )
    assert hosts.names() == ["lab-1"]
    assert "seed ignored" in caplog.text
    hosts.close()


def test_unchanged_seed_does_not_warn(
    tmp_path: Path, fake_daemon: Any, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "hosts.json"
    seed = {"lab-1": {"docker_url": "tcp://10.0.0.5:2375"}}
    _load(path, fake_daemon, seed).close()
    with caplog.at_level(logging.WARNING):
        _load(path, fake_daemon, seed).close()
    assert "seed ignored" not in caplog.text


@pytest.mark.parametrize(
    ("seed", "match"),
    [
        ({"Lab_1": {}}, "host name"),
        ({"a": {"default": True}, "b": {"default": True}}, "at most one default"),
        ({"a": {"tls": {"ca": "x"}}}, "missing required keys"),
        ({"a": {"colour": "red"}}, "colour"),
    ],
)
def test_bad_seed_is_rejected(
    tmp_path: Path, fake_daemon: Any, seed: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        _load(tmp_path / "hosts.json", fake_daemon, seed)


async def test_setting_default_clears_the_previous_one(
    tmp_path: Path, fake_daemon: Any
) -> None:
    hosts = _load(
        tmp_path / "hosts.json", fake_daemon, {"a": {"default": True}, "b": {}}
    )
    await hosts.patch("b", {"default": True}, in_use=False)
    assert hosts.default_host() == "b"
    assert hosts.spec("a").default is False
    assert hosts.docker_host("a").spec.default is False
    hosts.close()


async def test_soft_fields_change_in_use_without_recreating_the_host(
    tmp_path: Path, fake_daemon: Any
) -> None:
    hosts = _load(
        tmp_path / "hosts.json",
        fake_daemon,
        {"a": {"docker_url": "tcp://10.0.0.5:2375"}},
    )
    before = hosts.docker_host("a")
    await hosts.patch("a", {"drain": True, "registry": "mirror:5000"}, in_use=True)
    assert hosts.docker_host("a") is before
    assert before.spec.drain is True
    assert before.effective_registry == "mirror:5000"
    hosts.close()


async def test_hard_fields_refused_in_use_and_recreate_the_host_when_idle(
    tmp_path: Path, fake_daemon: Any
) -> None:
    hosts = _load(
        tmp_path / "hosts.json",
        fake_daemon,
        {"a": {"docker_url": "tcp://10.0.0.5:2375"}},
    )
    with pytest.raises(HostInUse):
        await hosts.patch("a", {"advertise_addr": "10.9.9.9"}, in_use=True)
    before = hosts.docker_host("a")
    await hosts.patch("a", {"advertise_addr": "10.9.9.9"}, in_use=False)
    assert hosts.docker_host("a") is not before
    assert hosts.docker_host("a").advertise_addr == "10.9.9.9"
    hosts.close()


async def test_put_persists_and_delete_refuses_in_use(
    tmp_path: Path, fake_daemon: Any
) -> None:
    path = tmp_path / "hosts.json"
    hosts = _load(path, fake_daemon, {"a": {}})
    await hosts.put("lab-9", HostSpec(docker_url="tcp://10.0.0.9:2375"), in_use=False)
    assert "lab-9" in json.loads(path.read_text())["hosts"]
    with pytest.raises(HostInUse):
        await hosts.delete("lab-9", in_use=True)
    await hosts.delete("lab-9", in_use=False)
    assert hosts.names() == ["a"]
    with pytest.raises(UnknownHost):
        hosts.spec("lab-9")
    hosts.close()


async def test_put_on_an_in_use_host_may_only_change_soft_fields(
    tmp_path: Path, fake_daemon: Any
) -> None:
    hosts = _load(
        tmp_path / "hosts.json",
        fake_daemon,
        {"a": {"docker_url": "tcp://10.0.0.5:2375"}},
    )
    await hosts.put(
        "a", HostSpec(docker_url="tcp://10.0.0.5:2375", drain=True), in_use=True
    )
    assert hosts.spec("a").drain is True
    with pytest.raises(HostInUse):
        await hosts.put("a", HostSpec(docker_url="tcp://10.0.0.6:2375"), in_use=True)
    hosts.close()


async def test_invalid_name_and_tls_are_rejected_at_runtime(
    tmp_path: Path, fake_daemon: Any
) -> None:
    hosts = _load(tmp_path / "hosts.json", fake_daemon, {"a": {}})
    with pytest.raises(ValueError, match="host name"):
        await hosts.put("Bad_Name", HostSpec(), in_use=False)
    with pytest.raises(ValueError, match="missing required keys"):
        await hosts.patch("a", {"tls": {"ca": "x"}}, in_use=False)
    hosts.close()
