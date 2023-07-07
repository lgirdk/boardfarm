"""Boardfarm core plugin."""

from argparse import Namespace
from collections import ChainMap
from collections.abc import Generator

from pluggy import PluginManager

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm3.devices.linux_tftp import LinuxTFTP
from boardfarm3.exceptions import EnvConfigError
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.lib.device_manager import DeviceManager


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
                device_config,
                cmdline_args,
            )
            device_manager.register_device(device_obj)
        else:
            msg = (
                f"{device_type} - Unknown boardfarm device, please register "
                f"{device_type} device using boardfarm_add_devices hook"
            )
            raise EnvConfigError(
                msg,
            )

    return device_manager


@hookimpl
def boardfarm_deploy_devices(
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
) -> DeviceManager:
    """Deploy registered devices to the environment.

    :param config: boardfarm config
    :param cmdline_args: command line arguments
    :param plugin_manager: plugin manager
    :returns: device manager with all deployed devices
    """
    device_manager: DeviceManager = plugin_manager.hook.boardfarm_register_devices(
        config=config,
        cmdline_args=cmdline_args,
        plugin_manager=plugin_manager,
    )
    plugin_manager.hook.validate_device_requirements(
        config=config,
        cmdline_args=cmdline_args,
        device_manager=device_manager,
    )
    plugin_manager.hook.boardfarm_server_boot(
        config=config,
        cmdline_args=cmdline_args,
        device_manager=device_manager,
    )
    plugin_manager.hook.boardfarm_server_configure(
        config=config,
        cmdline_args=cmdline_args,
        device_manager=device_manager,
    )
    plugin_manager.hook.boardfarm_device_boot(
        config=config,
        cmdline_args=cmdline_args,
        device_manager=device_manager,
    )
    plugin_manager.hook.boardfarm_device_configure(
        config=config,
        cmdline_args=cmdline_args,
        device_manager=device_manager,
    )
    plugin_manager.hook.boardfarm_attached_device_boot(
        config=config,
        cmdline_args=cmdline_args,
        device_manager=device_manager,
    )
    plugin_manager.hook.boardfarm_attached_device_configure(
        config=config,
        cmdline_args=cmdline_args,
        device_manager=device_manager,
    )
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
