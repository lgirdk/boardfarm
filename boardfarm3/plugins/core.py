"""Boardfarm core plugin."""

import logging
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from collections import ChainMap
from collections.abc import Generator
from typing import Any

from pluggy import PluginManager

from boardfarm3 import hookimpl
from boardfarm3.devices.axiros_acs import AxirosACS
from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm3.devices.genie_acs import GenieACS
from boardfarm3.devices.kamailio import SIPcenterKamailio5
from boardfarm3.devices.kea_provisioner import KeaProvisioner
from boardfarm3.devices.linux_lan import LinuxLAN
from boardfarm3.devices.linux_tftp import LinuxTFTP
from boardfarm3.devices.linux_wan import LinuxWAN
from boardfarm3.devices.linux_wlan import LinuxWLAN
from boardfarm3.devices.pjsip_phone import PJSIPPhone
from boardfarm3.devices.prplos_cpe import PrplDockerCPE
from boardfarm3.devices.rpirdkb_cpe import RPiRDKBCPE
from boardfarm3.exceptions import EnvConfigError
from boardfarm3.lib.boardfarm_config import BoardfarmConfig, parse_boardfarm_config
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
        required=False,
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
        required=False,
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
        default="",  # does not save the logs by default
        help="Save the console logs at the give location",
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
def boardfarm_parse_config(
    # pylint: disable=W0613
    cmdline_args: Namespace,  # noqa: ARG001
    inventory_config: dict[str, Any],
    env_config: dict[str, Any],
) -> BoardfarmConfig:
    """Parse the configs.

    This hook allows for the modification (if needed) of the configuration files.

    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param inventory_config: inventory json
    :type inventory_config: dict[str, Any]
    :param env_config: environment json
    :type env_config: dict[str, Any]
    :return: the boardfarmm config
    :rtype: BoardfarmConfig
    """
    return parse_boardfarm_config(inventory_config, env_config)


@hookimpl
def boardfarm_add_devices() -> dict[str, type[BoardfarmDevice]]:
    """Add devices to known devices for deployment.

    :returns: devices dictionary
    """
    return {
        "bf_tftp": LinuxTFTP,
        "bf_lan": LinuxLAN,
        "bf_wan": LinuxWAN,
        "bf_wlan": LinuxWLAN,
        "bf_acs": GenieACS,
        "bf_cpe": PrplDockerCPE,
        "bf_dhcp": KeaProvisioner,
        "bf_kamailio": SIPcenterKamailio5,
        "bf_phone": PJSIPPhone,
        "bf_rpi4rdkb": RPiRDKBCPE,
        "axiros_acs": AxirosACS,
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
