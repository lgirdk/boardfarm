"""Smoke tests for the __main__ entrypoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

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


def test_docker_launcher_runs_on_the_implicit_local_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BOARDFARM_PROFILES", '{"default": "img"}')
    monkeypatch.setenv("BOARDFARM_LAUNCHER", "docker")
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    monkeypatch.delenv("BOARDFARM_CONTROL_ID", raising=False)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "boardfarm3_control.__main__.uvicorn.run",
        lambda app, **_kwargs: captured.setdefault("app", app),
    )
    from boardfarm3_control.__main__ import main
    from boardfarm3_control.launcher import DockerLauncher

    main()
    launcher = captured["app"].state.launcher  # type: ignore[attr-defined]
    assert isinstance(launcher, DockerLauncher)
    assert launcher.host.name == "local"
    assert launcher.host.advertise_addr == "localhost"
    assert (tmp_path / "control_id").exists()
