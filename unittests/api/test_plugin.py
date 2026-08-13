"""Unit tests for the boardfarm API plugin."""

from argparse import Namespace

import pytest
from pluggy import PluginManager

from boardfarm3 import PROJECT_NAME, hookimpl
from boardfarm3.api import hookspecs, plugin
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.plugins import core as core_plugin
from boardfarm3.plugins.hookspecs import core as core_hookspecs


@pytest.fixture(name="plugin_manager")
def plugin_manager_fixture() -> PluginManager:
    """Build an isolated plugin manager with core and api plugins.

    :return: plugin manager
    :rtype: PluginManager
    """
    manager = PluginManager(PROJECT_NAME)
    manager.add_hookspecs(core_hookspecs)
    manager.register(core_plugin, "core")
    manager.register(plugin, "core_api")
    manager.add_hookspecs(hookspecs)
    return manager


def test_resolve_config_returns_boardfarm_config(
    plugin_manager: PluginManager,
    native_payload: dict,
) -> None:
    """The default hookimpl parses a native payload into a BoardfarmConfig.

    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    :param native_payload: native session payload
    :type native_payload: dict
    """
    args = Namespace(board_name="prplos-docker-1")
    config = plugin_manager.hook.boardfarm_api_resolve_config(
        payload=native_payload,
        cmdline_args=args,
        plugin_manager=plugin_manager,
    )
    assert isinstance(config, BoardfarmConfig)
    assert {device["name"] for device in config.get_devices_config()} >= {
        "board",
        "lan",
        "wan",
    }


def test_resolve_config_is_overridable_by_tryfirst_plugin(
    plugin_manager: PluginManager,
    native_payload: dict,
) -> None:
    """A plugin registering tryfirst wins over the default implementation.

    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    :param native_payload: native session payload
    :type native_payload: dict
    """
    sentinel = BoardfarmConfig({}, {}, [])

    class FrontendFormatPlugin:
        """Plugin that resolves a front-end specific payload format."""

        @staticmethod
        @hookimpl(tryfirst=True)
        def boardfarm_api_resolve_config(
            payload: dict,  # noqa: ARG004
            cmdline_args: Namespace,  # noqa: ARG004
            plugin_manager: PluginManager,  # noqa: ARG004
        ) -> BoardfarmConfig:
            """Return a fixed config.

            :param payload: opaque payload
            :type payload: dict
            :param cmdline_args: command line arguments
            :type cmdline_args: Namespace
            :param plugin_manager: plugin manager
            :type plugin_manager: PluginManager
            :return: boardfarm config
            :rtype: BoardfarmConfig
            """
            return sentinel

    plugin_manager.register(FrontendFormatPlugin(), "frontend_format")
    result = plugin_manager.hook.boardfarm_api_resolve_config(
        payload=native_payload,
        cmdline_args=Namespace(board_name="prplos-docker-1"),
        plugin_manager=plugin_manager,
    )
    assert result is sentinel


def test_resolve_config_trylast_yields_to_plain_override_registered_first(
    native_payload: dict,
) -> None:
    """Pin trylast itself: the tryfirst test above passes even without it.

    ``test_resolve_config_is_overridable_by_tryfirst_plugin`` cannot catch a
    regression where ``trylast=True`` is dropped from
    ``boardfarm3.api.plugin.boardfarm_api_resolve_config``: pluggy always
    runs ``tryfirst`` hookimpls before any non-``tryfirst`` one, no matter how
    the other hookimpl is marked. The construction that actually
    discriminates is a *plain* override registered *before* the default: with
    both plain, pluggy's LIFO tiebreak favours the later registration, so the
    default would incorrectly win unless it truly yields via ``trylast``.

    :param native_payload: native session payload
    :type native_payload: dict
    """
    manager = PluginManager(PROJECT_NAME)
    manager.add_hookspecs(core_hookspecs)
    manager.register(core_plugin, "core")
    manager.add_hookspecs(hookspecs)

    sentinel = BoardfarmConfig({}, {}, [])

    class PlainOverridePlugin:
        """Plugin that overrides using a plain (non-tryfirst) hookimpl."""

        @staticmethod
        @hookimpl
        def boardfarm_api_resolve_config(
            payload: dict,  # noqa: ARG004
            cmdline_args: Namespace,  # noqa: ARG004
            plugin_manager: PluginManager,  # noqa: ARG004
        ) -> BoardfarmConfig:
            """Return a fixed config.

            :param payload: opaque payload
            :type payload: dict
            :param cmdline_args: command line arguments
            :type cmdline_args: Namespace
            :param plugin_manager: plugin manager
            :type plugin_manager: PluginManager
            :return: boardfarm config
            :rtype: BoardfarmConfig
            """
            return sentinel

    # Registered *before* the default plugin. Both hookimpls are plain here,
    # so pluggy's LIFO tiebreak would make the later-registered one (the
    # default) win -- unless the default's trylast=True makes it yield
    # regardless of registration order.
    manager.register(PlainOverridePlugin(), "plain_override")
    manager.register(plugin, "core_api")

    result = manager.hook.boardfarm_api_resolve_config(
        payload=native_payload,
        cmdline_args=Namespace(board_name="prplos-docker-1"),
        plugin_manager=manager,
    )
    assert result is sentinel
