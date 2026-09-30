"""Smoke tests for the __main__ entrypoint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def test_main_raises_when_profiles_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that main raises ValueError when BOARDFARM_PROFILES is missing."""
    monkeypatch.delenv("BOARDFARM_PROFILES", raising=False)
    from boardfarm3_control.__main__ import main

    with pytest.raises(ValueError, match="BOARDFARM_PROFILES"):
        main()


def test_main_raises_when_profiles_not_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that main raises ValueError when BOARDFARM_PROFILES is invalid JSON."""
    monkeypatch.setenv("BOARDFARM_PROFILES", "not-json")
    from boardfarm3_control.__main__ import main

    with pytest.raises(ValueError, match="not valid JSON"):
        main()


def _run_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    monkeypatch.setenv("BOARDFARM_PROFILES", '{"default": "img"}')
    monkeypatch.setenv("BOARDFARM_LAUNCHER", "docker")
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "boardfarm3_control.__main__.uvicorn.run",
        lambda app, **_kwargs: captured.setdefault("app", app),
    )
    from boardfarm3_control.__main__ import main

    main()
    return captured["app"].state.launcher


def test_docker_launcher_is_multihost_on_the_implicit_local_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BOARDFARM_CONTROL_ID", raising=False)
    monkeypatch.delenv("BOARDFARM_HOSTS", raising=False)
    monkeypatch.delenv("BOARDFARM_HOSTS_FILE", raising=False)
    from boardfarm3_control.launcher import MultiHostLauncher

    launcher = _run_main(monkeypatch, tmp_path)
    assert isinstance(launcher, MultiHostLauncher)
    assert launcher.hosts.names() == ["local"]
    assert launcher.hosts.docker_host("local").advertise_addr == "localhost"
    assert (tmp_path / "control_id").exists()
    assert (tmp_path / "hosts.json").exists()
    launcher.hosts.close()


def test_seeded_hosts_default_registry_and_control_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "BOARDFARM_HOSTS",
        '{"lab-1": {"docker_url": "tcp://10.0.0.5:2375", "default": true}}',
    )
    monkeypatch.delenv("BOARDFARM_HOSTS_FILE", raising=False)
    monkeypatch.setenv("BOARDFARM_DEFAULT_REGISTRY", "mirror:5000")
    monkeypatch.setenv("BOARDFARM_CONTROL_ID", "lab-test")
    launcher = _run_main(monkeypatch, tmp_path)
    assert launcher.control_id == "lab-test"
    assert launcher.hosts.names() == ["lab-1"]
    assert launcher.hosts.docker_host("lab-1").effective_registry == "mirror:5000"
    launcher.hosts.close()


def test_hosts_and_hosts_file_together_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BOARDFARM_HOSTS", "{}")
    monkeypatch.setenv("BOARDFARM_HOSTS_FILE", str(tmp_path / "seed.json"))
    with pytest.raises(ValueError, match="not both"):
        _run_main(monkeypatch, tmp_path)
