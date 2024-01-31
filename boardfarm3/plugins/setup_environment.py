"""Boardfarm environment setup plugin."""

from argparse import Namespace

from pluggy import PluginManager

from boardfarm3 import hookimpl
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.lib.device_manager import DeviceManager
from boardfarm3.lib.interactive_shell import get_interactive_console_options


@hookimpl
def boardfarm_setup_env(
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
    device_manager: DeviceManager,
) -> DeviceManager:
    """Boardfarm environment setup for all the registered devices.

    :param config: boardfarm config
    :type config: BoardfarmConfig
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    :return: device manager with all devices environment setup
    :rtype: DeviceManager
    """
    if cmdline_args.skip_boot:
        plugin_manager.hook.boardfarm_skip_boot(
            config=config,
            cmdline_args=cmdline_args,
            device_manager=device_manager,
        )
        return device_manager
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


@hookimpl(trylast=True)
def boardfarm_post_setup_env(
    cmdline_args: Namespace,
    device_manager: DeviceManager,
) -> None:
    """Enter into boardfarm interactive session after boardfarm environment setup.

    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    get_interactive_console_options(device_manager, cmdline_args).show_table(
        "q",
        "exit",
    )
