"""Smoke tests for the __main__ entrypoint."""

from __future__ import annotations

import pytest


def test_main_raises_when_profiles_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that main raises ValueError when BOARDFARM_PROFILES is missing."""
    monkeypatch.delenv("BOARDFARM_PROFILES", raising=False)
    from boardfarm3_control.__main__ import main

    with pytest.raises(ValueError, match="BOARDFARM_PROFILES"):
        main()


def test_main_raises_when_profiles_not_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that main raises ValueError when BOARDFARM_PROFILES is invalid JSON."""
    monkeypatch.setenv("BOARDFARM_PROFILES", "not-json")
    from boardfarm3_control.__main__ import main

    with pytest.raises(ValueError, match="not valid JSON"):
        main()
