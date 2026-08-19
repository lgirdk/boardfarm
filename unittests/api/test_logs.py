"""Unit tests for agent artifact-directory resolution."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from boardfarm3.api import logs
from boardfarm3.api.logs import artifact_dir

if TYPE_CHECKING:
    import pytest


def test_artifact_dir_honours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", "/tmp/bf")  # noqa: S108
    assert artifact_dir("s-4f2a") == Path("/tmp/bf/s-4f2a")  # noqa: S108


def test_artifact_dir_uses_var_log_when_writable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOARDFARM_ARTIFACT_DIR", raising=False)
    monkeypatch.setattr(logs.os, "access", lambda *_: True)
    assert artifact_dir("s-4f2a") == Path("/var/log/boardfarm/s-4f2a")


def test_artifact_dir_falls_back_when_var_log_is_unwritable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-root agent must not crash every device connection on mkdir."""
    monkeypatch.delenv("BOARDFARM_ARTIFACT_DIR", raising=False)
    monkeypatch.setattr(logs.os, "access", lambda *_: False)
    expected = Path(tempfile.gettempdir()) / "boardfarm" / "s-4f2a"
    assert artifact_dir("s-4f2a") == expected


def test_artifact_dir_does_not_create_the_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    assert not artifact_dir("s-4f2a").exists()
