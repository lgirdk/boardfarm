"""Boardfarm core plugin."""

from argparse import Namespace
from collections import ChainMap
from typing import Dict, Generator, Type

from pluggy import PluginManager

from boardfarm import hookimpl
from boardfarm.devices.axiros_acs import AxirosACS
from boardfarm.devices.base_devices import BoardfarmDevice
from boardfarm.devices.linux_lan import LinuxLAN
from boardfarm.devices.linux_tftp import LinuxTFTP
from boardfarm.devices.linux_wan import LinuxWAN
from boardfarm.exceptions import EnvConfigError
from boardfarm.lib.boardfarm_config import BoardfarmConfig
from boardfarm.lib.device_manager import DeviceManager


@hookimpl
def boardfarm_add_devices() -> Dict[str, Type[BoardfarmDevice]]:
    """Add devices to known devices for deployment.

    :returns: devices dictionary
    """
    return {
        "debian_lan": LinuxLAN,
        "debian_wan": LinuxWAN,
        "debian_tftp": LinuxTFTP,
        "axiros_acs_soap": AxirosACS,
    }


@hookimpl
def boardfarm_register_devices(
    config: BoardfarmConfig, cmdline_args: Namespace, plugin_manager: PluginManager
) -> DeviceManager:
    """Register devices as plugin with boardfarm.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param plugin_manager: plugin manager
    :returns: device manager with all registered devices
    :raises EnvConfigError: when a device in inventory is unknown to boardfarm
    """
    device_manager = DeviceManager(plugin_manager)
    known_devices_list = ChainMap(*plugin_manager.hook.boardfarm_add_devices())
    for device_config in config.get_devices_config():
        device_type = device_config.get("type")
        if device_type in known_devices_list:
            device_obj = known_devices_list.get(device_type)(
                device_config, cmdline_args
            )
            device_manager.register_device(device_obj)
        else:
            raise EnvConfigError(
                f"{device_type} - Unknown boardfarm device, please register "
                f"{device_type} device using boardfarm_add_devices hook"
            )

    return device_manager


@hookimpl
def boardfarm_deploy_devices(
    config: BoardfarmConfig, cmdline_args: Namespace, plugin_manager: PluginManager
) -> DeviceManager:
    """Deploy registered devices to the environment.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param plugin_manager: plugin manager
    :returns: device manager with all deployed devices
    """
    device_manager: DeviceManager = plugin_manager.hook.boardfarm_register_devices(
        config=config, cmdline_args=cmdline_args, plugin_manager=plugin_manager
    )
    plugin_manager.hook.validate_device_requirements(
        config=config, cmdline_args=cmdline_args, device_manager=device_manager
    )
    plugin_manager.hook.boardfarm_server_boot(
        config=config, cmdline_args=cmdline_args, device_manager=device_manager
    )
    plugin_manager.hook.boardfarm_server_configure(
        config=config, cmdline_args=cmdline_args, device_manager=device_manager
    )
    plugin_manager.hook.boardfarm_device_boot(
        config=config, cmdline_args=cmdline_args, device_manager=device_manager
    )
    plugin_manager.hook.boardfarm_device_configure(
        config=config, cmdline_args=cmdline_args, device_manager=device_manager
    )
    plugin_manager.hook.boardfarm_attached_device_boot(
        config=config, cmdline_args=cmdline_args, device_manager=device_manager
    )
    plugin_manager.hook.boardfarm_attached_device_configure(
        config=config, cmdline_args=cmdline_args, device_manager=device_manager
    )
    return device_manager


@hookimpl(hookwrapper=True)
def boardfarm_release_devices(plugin_manager: PluginManager) -> Generator:
    """Shutdown all the devices before releasing them.

    :param plugin_manager: plugin manager instance
    """
    plugin_manager.hook.boardfarm_shutdown_device()
    yield
