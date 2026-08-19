"""Unit tests for the runtime agent entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from boardfarm3.api.__main__ import build_app_from_env

if TYPE_CHECKING:
    from pathlib import Path


def test_app_is_built_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Session id and board name come from the environment.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path: temporary directory path
    :type tmp_path: Path
    """
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("BOARDFARM_SESSION_ID", "s-9999")
    monkeypatch.setenv("BOARDFARM_BOARD_NAME", "prplos-docker-1")
    app = build_app_from_env()
    assert "prplos-docker-1" in app.title


def test_missing_board_name_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The agent refuses to start without a board name.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path: temporary directory path
    :type tmp_path: Path
    """
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("BOARDFARM_SESSION_ID", "s-9999")
    monkeypatch.delenv("BOARDFARM_BOARD_NAME", raising=False)
    with pytest.raises(ValueError, match="BOARDFARM_BOARD_NAME"):
        build_app_from_env()


def test_build_app_from_env_installs_agent_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A production agent must have an on-disk log before anything can fail.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path: temporary directory path
    :type tmp_path: Path
    """
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("BOARDFARM_BOARD_NAME", "board")
    monkeypatch.setenv("BOARDFARM_SESSION_ID", "s-4f2a")
    from boardfarm3.api.__main__ import build_app_from_env

    build_app_from_env()
    assert (tmp_path / "s-4f2a" / "agent.log").exists()
