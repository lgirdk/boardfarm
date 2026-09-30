"""The control id stamped on every container this control plane launches."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from boardfarm3_control.identity import resolve_control_id

if TYPE_CHECKING:
    from pathlib import Path


def test_env_wins_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_ID", "lab-prod")
    assert resolve_control_id(tmp_path) == "lab-prod"
    assert not (tmp_path / "control_id").exists()


def test_generated_once_and_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOARDFARM_CONTROL_ID", raising=False)
    first = resolve_control_id(tmp_path)
    assert first.startswith("c-")
    assert resolve_control_id(tmp_path) == first
    assert (tmp_path / "control_id").read_text().strip() == first


def test_invalid_env_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_ID", "has space")
    with pytest.raises(ValueError, match="BOARDFARM_CONTROL_ID"):
        resolve_control_id(tmp_path)
