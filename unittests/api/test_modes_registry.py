"""Collecting session modes from boardfarm_api plugins."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pluggy

from boardfarm3.api import hookspecs as api_hookspecs
from boardfarm3.api.entrypoints import DISABLED_PLUGINS_ENV
from boardfarm3.api.modes import boardfarm_argparser, collect_modes

from ._fake_mode import FakeMode

if TYPE_CHECKING:
    import pytest

hookimpl_api = pluggy.HookimplMarker("boardfarm_api")


class _Provides:
    @hookimpl_api
    def boardfarm_add_api_modes(self) -> dict[str, type[FakeMode]]:
        return {"fake": FakeMode}


class _Broken:
    @hookimpl_api
    def boardfarm_add_api_modes(self) -> dict[str, type[FakeMode]]:
        msg = "broken plugin"
        raise RuntimeError(msg)


class _Reserved:
    @hookimpl_api
    def boardfarm_add_api_modes(self) -> dict[str, type[FakeMode]]:
        return {"interact": FakeMode}


class _Malformed:
    @hookimpl_api
    def boardfarm_add_api_modes(self) -> list[str]:
        return ["fake"]


class _Mixed:
    @hookimpl_api
    def boardfarm_add_api_modes(self) -> dict[str, object]:
        return {"good": FakeMode, "bad": object, "worse": 42}


def _manager(*plugins: tuple[str, object]) -> pluggy.PluginManager:
    manager = pluggy.PluginManager("boardfarm_api")
    manager.add_hookspecs(api_hookspecs)
    for name, plugin in plugins:
        manager.register(plugin, name=name)
    return manager


def test_the_hookspec_is_declared() -> None:
    assert hasattr(_manager().hook, "boardfarm_add_api_modes")


def test_a_plugin_mode_is_collected_by_name() -> None:
    assert collect_modes(_manager(("fake_api", _Provides()))) == {"fake": FakeMode}


def test_a_raising_plugin_costs_only_its_own_modes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = _manager(("broken_api", _Broken()), ("fake_api", _Provides()))
    with caplog.at_level(logging.ERROR, logger="boardfarm3.api.modes"):
        assert collect_modes(manager) == {"fake": FakeMode}
    assert "broken_api" in caplog.text


def test_a_malformed_plugin_costs_only_its_own_modes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = _manager(("malformed_api", _Malformed()), ("fake_api", _Provides()))
    with caplog.at_level(logging.ERROR, logger="boardfarm3.api.modes"):
        assert collect_modes(manager) == {"fake": FakeMode}
    assert "malformed_api" in caplog.text


def test_a_contribution_that_is_not_a_session_mode_is_skipped_and_named(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = _manager(("mixed_api", _Mixed()))
    with caplog.at_level(logging.ERROR, logger="boardfarm3.api.modes"):
        assert collect_modes(manager) == {"good": FakeMode}
    errors = [
        record.getMessage()
        for record in caplog.records
        if record.name == "boardfarm3.api.modes" and record.levelno == logging.ERROR
    ]
    assert len(errors) == 2
    assert "mixed_api" in errors[0]
    assert "'bad'" in errors[0]
    assert "mixed_api" in errors[1]
    assert "'worse'" in errors[1]


def test_interact_cannot_be_taken_by_a_plugin() -> None:
    assert collect_modes(_manager(("sneaky_api", _Reserved()))) == {}


def test_a_disabled_plugin_offers_no_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "fake_api")
    assert collect_modes(_manager(("fake_api", _Provides()))) == {}


def test_without_a_plugin_manager_the_boardfarm_parser_is_empty() -> None:
    assert boardfarm_argparser(None).parse_args([]).__dict__ == {}
