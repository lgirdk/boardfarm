"""Tests for the boardfarm_api plugin deny-list."""

from __future__ import annotations

import pluggy
import pytest  # noqa: TC002 -- brief-mandated import, matches its verbatim test code

from boardfarm3.api import hookspecs as api_hookspecs
from boardfarm3.api.routers import (
    DISABLED_PLUGINS_ENV,
    RouterBundle,
    iter_plugin_bundles,
)

hookimpl_api = pluggy.HookimplMarker("boardfarm_api")


class _AlphaPlugin:
    """Contributes one bundle named alpha."""

    @hookimpl_api
    def boardfarm_add_api_routers(self) -> list[RouterBundle]:
        """Return the alpha bundle.

        :return: one bundle
        :rtype: list[RouterBundle]
        """
        return [RouterBundle(namespace="alpha")]


class _BetaPlugin:
    """Contributes one bundle named beta."""

    @hookimpl_api
    def boardfarm_add_api_routers(self) -> list[RouterBundle]:
        """Return the beta bundle.

        :return: one bundle
        :rtype: list[RouterBundle]
        """
        return [RouterBundle(namespace="beta")]


def _manager() -> pluggy.PluginManager:
    pm = pluggy.PluginManager("boardfarm_api")
    pm.add_hookspecs(api_hookspecs)
    pm.register(_AlphaPlugin(), name="alpha_api")
    pm.register(_BetaPlugin(), name="beta_api")
    return pm


def test_all_plugins_load_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DISABLED_PLUGINS_ENV, raising=False)
    names = {b.namespace for b in iter_plugin_bundles(_manager())}
    assert names == {"alpha", "beta"}


def test_named_plugin_is_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    names = {b.namespace for b in iter_plugin_bundles(_manager())}
    assert names == {"alpha"}


def test_disabled_plugin_does_not_leak_through_a_sibling_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disabled plugin must not contribute via another plugin's subset caller."""
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    bundles = list(iter_plugin_bundles(_manager()))
    assert [b.namespace for b in bundles] == ["alpha"]


def test_whitespace_and_empty_entries_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, " beta_api , ,")
    names = {b.namespace for b in iter_plugin_bundles(_manager())}
    assert names == {"alpha"}


def test_empty_value_disables_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "")
    names = {b.namespace for b in iter_plugin_bundles(_manager())}
    assert names == {"alpha", "beta"}
