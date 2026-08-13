"""Unit tests for the runtime agent entry point."""

import pytest

from boardfarm3.api.__main__ import build_app_from_env


def test_app_is_built_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Session id and board name come from the environment.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setenv("BOARDFARM_SESSION_ID", "s-9999")
    monkeypatch.setenv("BOARDFARM_BOARD_NAME", "prplos-docker-1")
    app = build_app_from_env()
    assert "prplos-docker-1" in app.title


def test_missing_board_name_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent refuses to start without a board name.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setenv("BOARDFARM_SESSION_ID", "s-9999")
    monkeypatch.delenv("BOARDFARM_BOARD_NAME", raising=False)
    with pytest.raises(ValueError, match="BOARDFARM_BOARD_NAME"):
        build_app_from_env()
