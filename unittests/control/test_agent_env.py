"""Tests that the control plane seeds the deny-list into agent environments."""

from __future__ import annotations

import pytest  # noqa: TC002 -- brief-mandated import, matches its verbatim test code

from boardfarm3.api.routers import DISABLED_PLUGINS_ENV
from boardfarm3_control.app import _agent_env


def test_env_is_seeded_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    assert _agent_env(None) == {DISABLED_PLUGINS_ENV: "beta_api"}


def test_request_value_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    assert _agent_env({DISABLED_PLUGINS_ENV: "other"}) == {
        DISABLED_PLUGINS_ENV: "other"
    }


def test_none_when_nothing_to_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DISABLED_PLUGINS_ENV, raising=False)
    assert _agent_env(None) is None


def test_other_request_env_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    assert _agent_env({"FOO": "bar"}) == {
        "FOO": "bar",
        DISABLED_PLUGINS_ENV: "beta_api",
    }
