"""Boardfarm main hook specifications."""

from argparse import ArgumentParser, Namespace
from typing import Any

from pluggy import PluginManager

from boardfarm3 import hookspec
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.lib.device_manager import DeviceManager

# pylint: disable=unused-argument


@hookspec
def boardfarm_add_hookspecs(plugin_manager: PluginManager) -> None:
    """Add new hookspecs to extend and/or update the framework.

    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    """


@hookspec
def boardfarm_add_cmdline_args(argparser: ArgumentParser) -> None:
    """Add new command line argument(s).

    :param argparser: argument parser
    :type argparser: ArgumentParser
    """


@hookspec(firstresult=True)
def boardfarm_cmdline_parse(
    argparser: ArgumentParser, cmdline_args: list[str]
) -> Namespace:
    """Parse command line arguments.

    :param argparser: argument parser
    :type argparser: ArgumentParser
    :param cmdline_args: command line arguments
    :type cmdline_args: list[str]
    :return: command line arguments
    :rtype: Namespace
    """


@hookspec
def boardfarm_configure(
    config: BoardfarmConfig, cmdline_args: Namespace, plugin_manager: PluginManager
) -> None:
    """Configure boardfarm based on command line arguments or environment config.

    This hook allows to register/deregister boardfarm plugins when you pass a
    command line argument. This way a plugin will be registered to boardfarm only
    when required.

    :param config: boardfarm config
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    """


@hookspec
def boardfarm_reserve_devices(
    config: BoardfarmConfig, cmdline_args: Namespace, plugin_manager: PluginManager
) -> None:
    """Reserve devices before starting the deployment.

    :param config: boardfarm config
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    """


@hookspec(firstresult=True)
def boardfarm_deploy_devices(
    config: BoardfarmConfig, cmdline_args: Namespace, plugin_manager: PluginManager
) -> DeviceManager:
    """Deploy all the devices to the environment.

    :param config: boardfarm config
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :return: device manager with all devices in the environment
    :rtype: DeviceManager
    """


@hookspec
def boardfarm_post_deploy_devices(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Call after all the devices are deployed to environment.

    :param config: boardfarm config
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def boardfarm_release_devices(
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
    deployment_status: dict[str, Any],
) -> None:
    """Release reserved devices after use.

    :param config: boardfarm config
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :param deployment_status: deployment status data
    :type deployment_status: Dict[str, Any]
    """
