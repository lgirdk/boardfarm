"""Boardfarm core plugin."""

import logging
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from collections import ChainMap
from collections.abc import Generator

from pluggy import PluginManager

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm3.devices.linux_tftp import LinuxTFTP
from boardfarm3.exceptions import EnvConfigError
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.lib.device_manager import DeviceManager
from boardfarm3.plugins.hookspecs import devices as Devices

_LOGGER = logging.getLogger(__name__)


def _non_empty_str(arg: str) -> str:
    """Type to check boardfarm/pytest command line arguments empty value.

    :param arg: command line argument
    :type arg: str
    :raises ArgumentTypeError: raises argparse ArgumentTypeError
                    for empty argument values
    :return: arg if the argument is non empty
    :rtype: str
    """
    if arg:
        return arg
    message = "Argument value should not be empty"
    raise ArgumentTypeError(message)


@hookimpl
def boardfarm_add_hookspecs(plugin_manager: PluginManager) -> None:
    """Add boardfarm core plugin hookspecs.

    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    """
    plugin_manager.add_hookspecs(Devices)


@hookimpl
def boardfarm_add_cmdline_args(argparser: ArgumentParser) -> None:
    """Add boardfarm command line arguments.

    :param argparser: argument parser
    :type argparser: ArgumentParser
    """
    argparser.add_argument(
        "--board-name",
        type=_non_empty_str,
        required=True,
        help="Board name",
    )
    argparser.add_argument(
        "--env-config",
        type=_non_empty_str,
        required=True,
        help="Environment JSON config file path",
    )
    argparser.add_argument(
        "--inventory-config",
        type=_non_empty_str,
        required=True,
        help="Inventory JSON config file path",
    )
    argparser.add_argument(
        "--legacy",
        action="store_true",
        help="allows for devices.<device> obj to be exposed (only for legacy use)",
    )
    argparser.add_argument(
        "--skip-boot",
        action="store_true",
        help="Skips the booting process, all devices will be used as they are",
    )
    argparser.add_argument(
        "--skip-contingency-checks",
        action="store_true",
        help="Skip contingency checks while running tests",
    )
    argparser.add_argument(
        "--save-console-logs",
        action="store_true",
        help="Save console logs to the disk",
    )
    argparser.add_argument(
        "--ignore-devices",
        default="",
        help=(
            "Ignore the given devices (names are comma separated)."
            " Useful when a device is incommunicado"
        ),
    )


@hookimpl
def boardfarm_cmdline_parse(
    argparser: ArgumentParser,
    cmdline_args: list[str],
) -> Namespace:
    """Parse command line arguments.

    :param argparser: argument parser instance
    :type argparser: ArgumentParser
    :param cmdline_args: command line arguments list
    :type cmdline_args: list[str]
    :return: command line arguments
    :rtype: Namespace
    """
    return argparser.parse_args(args=cmdline_args)


@hookimpl
def boardfarm_add_devices() -> dict[str, type[BoardfarmDevice]]:
    """Add devices to known devices for deployment.

    :returns: devices dictionary
    """
    return {
        "debian_tftp": LinuxTFTP,
    }


@hookimpl
def boardfarm_register_devices(
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
) -> DeviceManager:
    """Register devices as plugin with boardfarm.

    :param config: boardfarm config
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    :raises EnvConfigError: when a device in inventory is unknown to boardfarm
    :return: device manager with all registered devices
    :rtype: DeviceManager
    """
    device_manager = DeviceManager(plugin_manager)
    known_devices_list = ChainMap(*plugin_manager.hook.boardfarm_add_devices())
    to_be_ignored = cmdline_args.ignore_devices.split(",")
    for device_config in config.get_devices_config():
        if device_config.get("name") in to_be_ignored:
            _LOGGER.warning("Ignoring '%s'", device_config.get("name"))
            continue
        device_type = device_config.get("type")
        if device_type in known_devices_list:
            device_obj = known_devices_list.get(device_type)(
                device_config,
                cmdline_args,
            )
            device_manager.register_device(device_obj)
        else:
            msg = (
                f"{device_type} - Unknown boardfarm device, please register "
                f"{device_type} device using boardfarm_add_devices hook"
            )
            raise EnvConfigError(msg)

    return device_manager


@hookimpl(hookwrapper=True)
def boardfarm_release_devices(
    plugin_manager: PluginManager,
) -> Generator[None, None, None]:
    """Shutdown all the devices before releasing them.

    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :yield: None
    :rtype: Generator[None,None,None]
    """
    plugin_manager.hook.boardfarm_shutdown_device()
    yield
