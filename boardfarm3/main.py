"""Boardfarm main module."""

import logging.config
import sys
from argparse import ArgumentParser
from typing import Any

from pluggy import PluginManager

from boardfarm3 import PROJECT_NAME
from boardfarm3.configs import LOGGING_CONFIG
from boardfarm3.lib.boardfarm_config import parse_boardfarm_config
from boardfarm3.plugins.hookspecs import core

# pylint: disable=no-member  # plugin_manager.hook.* calls are dynamic


_BOARDFARM_PLUGIN_MANAGER: PluginManager = None


def get_plugin_manager() -> PluginManager:
    """Get boardfarm plugin manager.

    :return: boardfarm plugin manager
    :rtype: PluginManager
    """
    global _BOARDFARM_PLUGIN_MANAGER  # pylint: disable=global-statement  # noqa: PLW0603, E501
    if _BOARDFARM_PLUGIN_MANAGER is not None:
        return _BOARDFARM_PLUGIN_MANAGER
    plugin_manager = PluginManager(PROJECT_NAME)
    plugin_manager.add_hookspecs(core)
    plugin_manager.load_setuptools_entrypoints(PROJECT_NAME)
    plugin_manager.hook.boardfarm_add_hookspecs(plugin_manager=plugin_manager)
    _BOARDFARM_PLUGIN_MANAGER = plugin_manager
    return plugin_manager


def main() -> None:
    """Boardfarm main function.

    :raises Exception: when the deployment fails
    """
    logging.config.dictConfig(LOGGING_CONFIG)
    argparser = ArgumentParser(PROJECT_NAME)
    plugin_manager = get_plugin_manager()
    plugin_manager.hook.boardfarm_add_cmdline_args(argparser=argparser)
    cmdline_args = plugin_manager.hook.boardfarm_cmdline_parse(
        argparser=argparser,
        cmdline_args=sys.argv[1:],
    )
    plugin_manager.hook.boardfarm_configure(
        cmdline_args=cmdline_args,
        plugin_manager=plugin_manager,
    )
    inventory_config = plugin_manager.hook.boardfarm_reserve_devices(
        cmdline_args=cmdline_args,
        plugin_manager=plugin_manager,
    )
    config = parse_boardfarm_config(inventory_config, cmdline_args.env_config)
    deployment_status: dict[str, Any] = {}
    try:
        device_manager = plugin_manager.hook.boardfarm_register_devices(
            config=config,
            cmdline_args=cmdline_args,
            plugin_manager=plugin_manager,
        )
        plugin_manager.hook.boardfarm_setup_env(
            config=config,
            cmdline_args=cmdline_args,
            plugin_manager=plugin_manager,
            device_manager=device_manager,
        )
        plugin_manager.hook.boardfarm_post_setup_env(
            config=config,
            cmdline_args=cmdline_args,
            device_manager=device_manager,
        )
        deployment_status = {"status": "success"}
    except Exception:  # pylint: disable=broad-except
        deployment_status = {"status": "failed", "exception": sys.exc_info()[1]}
        raise
    finally:
        plugin_manager.hook.boardfarm_release_devices(
            cmdline_args=cmdline_args,
            plugin_manager=plugin_manager,
            deployment_status=deployment_status,
        )


if __name__ == "__main__":
    main()
