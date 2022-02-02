"""Boardfarm main module."""

import logging.config
import sys
from argparse import ArgumentParser

from pluggy import PluginManager

from boardfarm import PROJECT_NAME
from boardfarm.configs import LOGGING_CONFIG
from boardfarm.lib.boardfarm_config import parse_boardfarm_config
from boardfarm.plugins.hookspecs import core

# pylint: disable=no-member  # plugin_manager.hook.* calls are dynamic


def get_plugin_manager() -> PluginManager:
    """Get boardfarm plugin manager.

    :return: boardfarm plugin manager
    """
    plugin_manager = PluginManager(PROJECT_NAME)
    plugin_manager.add_hookspecs(core)
    plugin_manager.load_setuptools_entrypoints(PROJECT_NAME)
    plugin_manager.hook.boardfarm_add_hookspecs(plugin_manager=plugin_manager)
    return plugin_manager


def main() -> None:
    """Boardfarm main function."""
    logging.config.dictConfig(LOGGING_CONFIG)
    argparser = ArgumentParser(PROJECT_NAME)
    plugin_manager = get_plugin_manager()
    plugin_manager.hook.boardfarm_add_cmdline_args(argparser=argparser)
    cmdline_args = plugin_manager.hook.boardfarm_cmdline_parse(
        argparser=argparser, cmdline_args=sys.argv[1:]
    )
    config = parse_boardfarm_config(
        cmdline_args.board_name, cmdline_args.env_config, cmdline_args.inventory_config
    )
    plugin_manager.hook.boardfarm_configure(
        config=config, cmdline_args=cmdline_args, plugin_manager=plugin_manager
    )
    try:
        plugin_manager.hook.boardfarm_reserve_devices(
            config=config, cmdline_args=cmdline_args, plugin_manager=plugin_manager
        )
        device_manager = plugin_manager.hook.boardfarm_deploy_devices(
            config=config, cmdline_args=cmdline_args, plugin_manager=plugin_manager
        )
        plugin_manager.hook.boardfarm_post_deploy_devices(
            config=config, cmdline_args=cmdline_args, device_manager=device_manager
        )
    finally:
        plugin_manager.hook.boardfarm_release_devices(
            config=config, cmdline_args=cmdline_args, plugin_manager=plugin_manager
        )


if __name__ == "__main__":
    main()
