"""Shared fixtures for control plane tests."""

from __future__ import annotations

import pytest

from boardfarm3_control.launcher import FakeLauncher


@pytest.fixture
def fake_launcher() -> FakeLauncher:
    """Return a fresh FakeLauncher with no sessions."""
    return FakeLauncher()


@pytest.fixture
def profiles() -> dict[str, str]:
    """Return a minimal profile map for tests."""
    return {"prplos": "boardfarm3-agent:latest"}
