"""Boardfarm main hook specifications."""

from argparse import ArgumentParser, Namespace
from typing import Any

from pluggy import PluginManager

from boardfarm3 import hookspec
from boardfarm3.devices.base_devices import BoardfarmDevice
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
def boardfarm_parse_config(
    cmdline_args: Namespace,
    inventory_config: dict[str, Any],
    env_config: dict[str, Any],
) -> BoardfarmConfig:
    """Parse the config.

    This hook allows for the modification (if needed) of the configuration files,
    like inventory and environment, by using cmd line overrides.

    # noqa: DAR202

    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param inventory_config: inventory json
    :type inventory_config: dict[str, Any]
    :param env_config: environment json
    :type env_config: dict[str, Any]
    :return: a BoardfarmConfig object
    :rtype: BoardfarmConfig
    """


@hookspec(firstresult=True)
def boardfarm_cmdline_parse(
    argparser: ArgumentParser,
    cmdline_args: list[str],
) -> Namespace:
    """Parse command line arguments.

    # noqa: DAR202

    :param argparser: argument parser
    :type argparser: ArgumentParser
    :param cmdline_args: command line arguments
    :type cmdline_args: list[str]
    :return: command line arguments
    :rtype: Namespace
    """


@hookspec
def boardfarm_configure(cmdline_args: Namespace, plugin_manager: PluginManager) -> None:
    """Configure boardfarm based on command line arguments or environment config.

    This hook allows to register/deregister boardfarm plugins when you pass a
    command line argument. This way a plugin will be registered to boardfarm only
    when required.

    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    """


@hookspec(firstresult=True)
def boardfarm_reserve_devices(
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
) -> dict[str, Any]:
    """Reserve devices before starting the deployment.

    This hook is used to reserve devices before deployment.

    # noqa: DAR202
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :return: inventory configuration
    :rtype: dict[str, Any]
    """


@hookspec(firstresult=True)
def boardfarm_setup_env(
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
    device_manager: DeviceManager,
) -> DeviceManager:
    """Boardfarm environment setup for all the devices.

    This hook is used to deploy boardfarm devices.

    # noqa: DAR202
    :param config: boardfarm config
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    :return: device manager with all devices in the environment
    :rtype: DeviceManager
    """


@hookspec
def boardfarm_post_setup_env(
    cmdline_args: Namespace,
    device_manager: DeviceManager,
) -> None:
    """Call after the environment setup is completed for all the devices.

    This hook is used to perform required operations after the board is deployed.

    # noqa: DAR202
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

    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :param deployment_status: deployment status data
    :type deployment_status: Dict[str, Any]
    """


@hookspec(firstresult=True)
def boardfarm_register_devices(
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
) -> DeviceManager:
    """Register device to plugin manager.

    This hook is responsible to register devices to the device manager after
    initialization based on the given inventory and environment config.

    # noqa: DAR202
    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :return: device manager with all registered devices
    :rtype: DeviceManager
    """


@hookspec
def boardfarm_add_devices() -> dict[str, type[BoardfarmDevice]]:
    """Add devices to known devices list.

    This hook is used to let boardfarm know the devices which are configured
    in the inventory config.
    Each repo with a boardfarm device should implement this hook to add each
    devices to the list of known devices.

    # noqa: DAR202
    :return: dictionary with device name and class
    :rtype: dict[str, type[BoardfarmDevice]]
    """


@hookspec
def boardfarm_shutdown_device() -> None:
    """Shutdown boardfarm device after use.

    This hook should be used by a device to perform a clean shutdown of a device
    after releasing all the resources (e.g. close all of the open ssh connections)
    before the shutdown of the framework.
    """
