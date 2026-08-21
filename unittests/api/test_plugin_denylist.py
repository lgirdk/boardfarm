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


class _GammaPlugin:
    """Contributes one bundle named gamma."""

    @hookimpl_api
    def boardfarm_add_api_routers(self) -> list[RouterBundle]:
        """Return the gamma bundle.

        :return: one bundle
        :rtype: list[RouterBundle]
        """
        return [RouterBundle(namespace="gamma")]


def _manager() -> pluggy.PluginManager:
    pm = pluggy.PluginManager("boardfarm_api")
    pm.add_hookspecs(api_hookspecs)
    pm.register(_AlphaPlugin(), name="alpha_api")
    pm.register(_BetaPlugin(), name="beta_api")
    return pm


def _three_plugin_manager() -> pluggy.PluginManager:
    pm = pluggy.PluginManager("boardfarm_api")
    pm.add_hookspecs(api_hookspecs)
    pm.register(_AlphaPlugin(), name="alpha_api")
    pm.register(_BetaPlugin(), name="beta_api")
    pm.register(_GammaPlugin(), name="gamma_api")
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
    """Disabling the middle of three plugins must not affect its siblings.

    With alpha, beta, and gamma all registered and only beta disabled, both
    of beta's siblings must still contribute their bundles independently —
    proving the exclusion is per-plugin-name, not a side effect of caller
    order or of only two plugins being registered (which the simpler
    two-plugin test above cannot distinguish from "the wrong plugin was
    excluded").
    """
    monkeypatch.setenv(DISABLED_PLUGINS_ENV, "beta_api")
    bundles = list(iter_plugin_bundles(_three_plugin_manager()))
    namespaces = [b.namespace for b in bundles]
    assert "alpha" in namespaces
    assert "gamma" in namespaces
    assert "beta" not in namespaces
    assert set(namespaces) == {"alpha", "gamma"}


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
