"""Runtime agent entry point."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import uvicorn

from boardfarm3.api.app import create_app
from boardfarm3.api.logs import install_agent_log

if TYPE_CHECKING:
    from fastapi import FastAPI

# uvicorn's exit code when the server could not start.
_STARTUP_FAILURE = 3


def _session_id() -> str:
    return os.environ.get("BOARDFARM_SESSION_ID", "s-local")


def build_app_from_env() -> FastAPI:
    """Build the agent application from environment variables.

    :raises ValueError: when BOARDFARM_BOARD_NAME is not set
    :return: FastAPI application
    :rtype: FastAPI
    """
    board_name = os.environ.get("BOARDFARM_BOARD_NAME", "")
    if not board_name:
        msg = "BOARDFARM_BOARD_NAME must be set"
        raise ValueError(msg)
    session_id = _session_id()
    install_agent_log(session_id)
    return create_app(session_id, board_name)


def main() -> None:
    """Run the agent under uvicorn."""
    config = uvicorn.Config(
        build_app_from_env(),
        host="0.0.0.0",  # noqa: S104
        port=int(os.environ.get("BOARDFARM_AGENT_PORT", "8000")),
        loop="asyncio",  # nest_asyncio (used by lgi-shared) cannot patch uvloop
    )
    # Config() has just applied uvicorn's logging dictConfig, which strips
    # every handler from the uvicorn loggers: re-attach the agent log.
    install_agent_log(_session_id())
    server = uvicorn.Server(config)
    server.run()
    if not server.started:
        sys.exit(_STARTUP_FAILURE)


if __name__ == "__main__":
    main()
