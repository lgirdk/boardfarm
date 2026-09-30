"""Helpers shared by the launcher implementations."""

from __future__ import annotations

import socket

# Matches boardfarm3.api.logs's default artifact root. Duplicated here rather
# than imported: boardfarm3_control is a separate deployable from boardfarm3
# and must not take on a hard runtime dependency on the agent package to
# resolve a single fallback string.
_DEFAULT_ARTIFACT_ROOT = "/var/log/boardfarm"


def _artifact_root(agent_env: dict[str, str] | None) -> str:
    """Resolve the artifact root a launched agent will use.

    :param agent_env: extra environment variables passed to the agent
    :type agent_env: dict[str, str] | None
    :return: ``BOARDFARM_ARTIFACT_DIR`` override, or the shared default
    :rtype: str
    """
    return (agent_env or {}).get("BOARDFARM_ARTIFACT_DIR") or _DEFAULT_ARTIFACT_ROOT


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]
