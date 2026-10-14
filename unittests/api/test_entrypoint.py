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


_LOGGERS = ("boardfarm3", "uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture(name="restore_loggers")
def restore_loggers_fixture() -> object:
    """Put the agent's and uvicorn's loggers back the way they were.

    :yield: None
    :rtype: object
    """
    import logging

    saved = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in _LOGGERS
    }
    yield
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if handler not in handlers:
                logger.removeHandler(handler)
                handler.close()
        logger.setLevel(level)
        logger.propagate = propagate


@pytest.mark.usefixtures("restore_loggers")
def test_agent_log_keeps_uvicorn_lines_after_uvicorn_configures_logging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Uvicorn's own dictConfig must not strip the agent log from its loggers.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path: temporary directory path
    :type tmp_path: Path
    """
    import logging

    import uvicorn

    from boardfarm3.api import __main__ as entrypoint

    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("BOARDFARM_BOARD_NAME", "board")
    monkeypatch.setenv("BOARDFARM_SESSION_ID", "s-4f2a")

    def fake_serve(server: uvicorn.Server, sockets: object = None) -> None:  # noqa: ARG001
        server.started = True
        logging.getLogger("uvicorn.error").info("uvicorn says hello")

    monkeypatch.setattr(uvicorn.Server, "run", fake_serve)
    entrypoint.main()
    text = (tmp_path / "s-4f2a" / "agent.log").read_text(encoding="utf-8")
    assert "uvicorn says hello" in text


@pytest.mark.usefixtures("restore_loggers")
def test_installing_the_agent_log_twice_writes_each_line_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Re-installing (after uvicorn configures logging) must not duplicate lines.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path: temporary directory path
    :type tmp_path: Path
    """
    import logging

    from boardfarm3.api.logs import install_agent_log

    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    install_agent_log("s-1")
    install_agent_log("s-1")
    logging.getLogger("boardfarm3.demo").warning("exactly once")
    text = (tmp_path / "s-1" / "agent.log").read_text(encoding="utf-8")
    assert text.count("exactly once") == 1
