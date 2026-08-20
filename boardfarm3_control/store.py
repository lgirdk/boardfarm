"""On-disk store for archived agent diagnostics."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

_DEFAULT_ROOT = "/var/lib/boardfarm-control"
_log = logging.getLogger(__name__)


class DiagnosticsStore:
    """Per-session directory of archived bundles and metadata.

    ``meta.json`` outlives both the container and the bundle, so a dead
    session stays listable and explicable after either has been purged.
    """

    def __init__(self, root: Path | None = None) -> None:
        """Initialise the store.

        :param root: store root; ``$BOARDFARM_CONTROL_STORE`` when omitted
        :type root: Path | None
        """
        self._root = root or Path(
            os.environ.get("BOARDFARM_CONTROL_STORE") or _DEFAULT_ROOT,
        )

    def session_dir(self, session_id: str) -> Path:
        """Return the directory holding a session's artifacts.

        :param session_id: session identifier
        :type session_id: str
        :return: session directory
        :rtype: Path
        """
        return self._root / "sessions" / session_id

    def bundle_path(self, session_id: str) -> Path:
        """Return the archived bundle path for a session.

        :param session_id: session identifier
        :type session_id: str
        :return: bundle path
        :rtype: Path
        """
        return self.session_dir(session_id) / "bundle.tar.gz"

    def has_bundle(self, session_id: str) -> bool:
        """Report whether an archived bundle exists.

        :param session_id: session identifier
        :type session_id: str
        :return: True when a bundle is on disk
        :rtype: bool
        """
        return self.bundle_path(session_id).is_file()

    def write_meta(self, session_id: str, meta: dict[str, Any]) -> None:
        """Persist session metadata.

        :param session_id: session identifier
        :type session_id: str
        :param meta: metadata to store
        :type meta: dict[str, Any]
        """
        directory = self.session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "meta.json").write_text(
            json.dumps(meta, indent=2),
            encoding="utf-8",
        )

    def read_meta(self, session_id: str) -> dict[str, Any] | None:
        """Read session metadata.

        :param session_id: session identifier
        :type session_id: str
        :return: metadata, or None when absent or unreadable
        :rtype: dict[str, Any] | None
        """
        path = self.session_dir(session_id) / "meta.json"
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data

    def write_bundle(self, session_id: str, chunks: Iterable[bytes]) -> int:
        """Write an archived bundle from an iterable of byte chunks.

        :param session_id: session identifier
        :type session_id: str
        :param chunks: bundle payload
        :type chunks: Iterable[bytes]
        :return: number of bytes written
        :rtype: int
        """
        path = self.bundle_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with path.open("wb") as handle:
            for chunk in chunks:
                handle.write(chunk)
                written += len(chunk)
        return written

    def list_sessions(self) -> list[str]:
        """Return every session id present in the store.

        :return: session identifiers
        :rtype: list[str]
        """
        base = self._root / "sessions"
        if not base.is_dir():
            return []
        return [entry.name for entry in base.iterdir() if entry.is_dir()]

    def total_bytes(self) -> int:
        """Return the total size of the store in bytes.

        :return: byte count
        :rtype: int
        """
        base = self._root / "sessions"
        if not base.is_dir():
            return 0
        return sum(p.stat().st_size for p in base.rglob("*") if p.is_file())

    def delete(self, session_id: str) -> None:
        """Delete every artifact for a session.

        :param session_id: session identifier
        :type session_id: str
        """
        shutil.rmtree(self.session_dir(session_id), ignore_errors=True)
