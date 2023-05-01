"""
Boardfarm device hook specifications.

A Boardfarm device should belong to one of the following categories:

    1. server, i.e. DHCP, ACS...
    2. device, i.e. a connectivity CPE
    3. attached device, i.e. a LAN client


Every device should fulfill the following responsibilities at
different stages of the deployment.

Hook responsibilities:

    1. skip boot
        - device can be interacted with as it is without making
          any changes to it

    2. boot
        - device is running with required software
        - device can be interacted with, e.g. via console
        - device has a management IP address or direct console access
          if the device has a console

    3. configure
        - all of the points from boot
        - user driven configurations are applied to the device
        - device has a service IP address if applicable
            Eg: A CPE device has access network IP address,
                eRouter IP, except in disabled mode, eMTA IP
        - for Wi-Fi clients, no connection to the Wi-Fi network
          is made and no IP address on service interface is assigned
"""

from argparse import Namespace
from typing import Any

from pluggy import PluginManager

from boardfarm3 import hookspec
from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.lib.device_manager import DeviceManager

# pylint: disable=unused-argument


@hookspec(firstresult=True)
def boardfarm_register_devices(
    config: BoardfarmConfig, cmdline_args: Namespace, plugin_manager: PluginManager
) -> DeviceManager:
    """Register device to plugin manager.

    This hook is responsible to register devices to the device manager after
    initialization based on the given inventory and environment config.

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

    :return: dictionary with device name and class
    :rtype: dict[str, type[BoardfarmDevice]]
    """


@hookspec
def validate_device_requirements(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Validate device requirements.

    This hook is responsible to validate the requirements of a device before
    deploying devices to the environment.
    This allows us to fail the deployment early.

    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def boardfarm_server_boot(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Boot boardfarm server device.

    This hook should be used to boot a device which is not dependent on other
    devices in the environment. E.g. WAN and CMTS.

    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def boardfarm_server_configure(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Configure boardfarm server device.

    This hook should be used to configure a device, after having it booted,
    which is not dependent on other devices in the environment. E.g. WAN and CMTS

    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def boardfarm_device_boot(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Boot boardfarm device.

    This hook should be used to boot a device which is dependent on one or more
    servers in the environment. E.g. CPE.

    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def boardfarm_device_configure(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Configure boardfarm device.

    This hook should be used to configure a device, after having it booted,
    which is dependent on one or more servers in the environment. E.g. CPE.

    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def boardfarm_attached_device_boot(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Boot boardfarm attached device.

    This hook should be used to boot a device which is attached to a device
    in the environment. E.g. LAN.

    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def boardfarm_attached_device_configure(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Configure boardfarm attached device.

    This hook should be used to configure a device, after having it booted,
    which is attached to a device in the environment. E.g. LAN.

    :param config: boardfarm config instance
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def contingency_check(env_req: dict[str, Any], device_manager: DeviceManager) -> None:
    """Perform contingency check to make sure the device is working fine before use.

    This hook could be used by any device.
    It is used by the pytest-boardfarm plugin to make sure the device is in
    good condition before running each test.

    :param env_req: environment request dictionary
    :type env_req: dict[str, Any]
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """


@hookspec
def boardfarm_shutdown_device() -> None:
    """Shutdown boardfarm device after use.

    This hook should be used by a device to perform a clean shutdown of a device
    after releasing all the resources (e.g. close all of the open ssh connections)
    before the shutdown of the framework.
    """
