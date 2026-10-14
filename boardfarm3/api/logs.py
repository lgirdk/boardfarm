"""Artifact directory resolution and agent log file installation."""

from __future__ import annotations

import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

_DEFAULT_ROOT = "/var/log/boardfarm"
_LOG_BYTES = 10 * 1024 * 1024
_LOG_BACKUPS = 3
_ATTACH_TO = ("boardfarm3", "uvicorn", "uvicorn.error", "uvicorn.access")

_log = logging.getLogger(__name__)
# One handler per log file, so installing again re-attaches instead of
# duplicating every line.
_HANDLERS: dict[Path, RotatingFileHandler] = {}


def _root() -> Path:
    """Return the artifact root, falling back when the default is unwritable.

    Console logging is unconditional, so device connections will ``mkdir``
    under this root on every connect. A non-root agent (ProcessLauncher, local
    development, integration tests) cannot write to ``/var/log``, and letting
    that raise would crash every device connection.

    :return: writable artifact root
    :rtype: Path
    """
    explicit = os.environ.get("BOARDFARM_ARTIFACT_DIR")
    if explicit:
        return Path(explicit)
    default = Path(_DEFAULT_ROOT)
    probe = default if default.exists() else default.parent
    if os.access(probe, os.W_OK):
        return default
    return Path(tempfile.gettempdir()) / "boardfarm"


def artifact_dir(session_id: str) -> Path:
    """Return the artifact directory for a session.

    The directory is not created — device connections create it lazily when
    they attach their own console log handlers.

    :param session_id: session identifier
    :type session_id: str
    :return: per-session artifact directory
    :rtype: Path
    """
    return _root() / session_id


def install_agent_log(session_id: str) -> Path | None:
    """Attach a rotating file handler capturing framework and uvicorn logs.

    Best-effort: an unwritable artifact directory is logged and ignored rather
    than preventing the agent from starting. Idempotent: calling it again
    re-attaches the same handler to any logger that lost it (uvicorn's
    logging dictConfig removes handlers from the ``uvicorn*`` loggers).

    :param session_id: session identifier
    :type session_id: str
    :return: path of the log file, or None when it could not be created
    :rtype: Path | None
    """
    directory = artifact_dir(session_id)
    path = directory / "agent.log"
    handler = _HANDLERS.get(path)
    if handler is None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                path,
                maxBytes=_LOG_BYTES,
                backupCount=_LOG_BACKUPS,
                encoding="utf-8",
            )
        except OSError as exc:
            _log.warning("could not open agent log in %s: %s", directory, exc)
            return None
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"),
        )
        _HANDLERS[path] = handler
    for name in _ATTACH_TO:
        logger = logging.getLogger(name)
        if handler not in logger.handlers:
            logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return path
