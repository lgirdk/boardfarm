"""Runtime agent entry point."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import uvicorn

from boardfarm3.api.app import create_app

if TYPE_CHECKING:
    from fastapi import FastAPI


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
    session_id = os.environ.get("BOARDFARM_SESSION_ID", "s-local")
    return create_app(session_id, board_name)


def main() -> None:
    """Run the agent under uvicorn."""
    uvicorn.run(
        build_app_from_env(),
        host="0.0.0.0",  # noqa: S104
        port=int(os.environ.get("BOARDFARM_AGENT_PORT", "8000")),
        loop="asyncio",  # nest_asyncio (used by lgi-shared) cannot patch uvloop
    )


if __name__ == "__main__":
    main()
