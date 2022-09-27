"""Boardfarm device hook specifications."""

from argparse import Namespace

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
    """Register devices to plugin manager.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param plugin_manager: plugin manager
    :returns: device manager with all deployed devices
    """


@hookspec
def boardfarm_add_devices() -> dict[str, type[BoardfarmDevice]]:
    """Add devices to known devices list.

    :returns: added devices to boardfarm
    """


@hookspec
def validate_device_requirements(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Validate device requirements.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param device_manager: device manager
    """


@hookspec
def boardfarm_server_boot(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Boot boardfarm server device.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param device_manager: device manager
    """


@hookspec
def boardfarm_server_configure(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Configure boardfarm server device.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param device_manager: device manager
    """


@hookspec
def boardfarm_device_boot(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Boot boardfarm device.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param device_manager: device manager
    """


@hookspec
def boardfarm_device_configure(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Configure boardfarm device.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param device_manager: device manager
    """


@hookspec
def boardfarm_attached_device_boot(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Boot boardfarm attached device.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param device_manager: device manager
    """


@hookspec
def boardfarm_attached_device_configure(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Configure boardfarm attached device.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param device_manager: device manager
    """


@hookspec
def boardfarm_shutdown_device() -> None:
    """Shutdown boardfarm device after use."""
