"""Boardfarm environment setup plugin."""

import asyncio
import logging
import time
from argparse import Namespace
from sys import version_info

from pluggy import PluginManager

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.lib.device_manager import DeviceManager
from boardfarm3.lib.interactive_shell import get_interactive_console_options

IS_TASKGROUP_AVAILABLE = version_info >= (3, 11)
_LOGGER = logging.getLogger(__name__)


def _is_async_hook_supported(hook_name: str, device_manager: DeviceManager) -> bool:
    if not IS_TASKGROUP_AVAILABLE:
        return False
    # we can run asyncio if and only if all devices have both async and blocking
    # hook implementations
    async_hook_name = f"{hook_name}_async"
    # set of devices with blocking implementation:
    bio_set = {
        device
        for device in device_manager.get_devices_by_type(BoardfarmDevice).values()
        if hasattr(device, hook_name)
    }
    # set of devices with non-blocking implementation:
    aio_set = {
        device
        for device in device_manager.get_devices_by_type(BoardfarmDevice).values()
        if hasattr(device, async_hook_name)
    }
    if aio_set == bio_set:
        return True
    # inform the user about the devices that are missing the asyncio implementation
    for device in bio_set - aio_set:
        _LOGGER.warning(
            "Consider adding the implementation of %s to %s. "
            "It would allow the full usage of asyncio at this stage.",
            async_hook_name,
            device.device_name,
        )
    return False


async def _run_hook_async(
    hook_name: str,
    plugin_manager: PluginManager,
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    device_manager: DeviceManager,
) -> None:
    start_time = time.monotonic()
    async_hook_name = f"{hook_name}_async"
    async with asyncio.TaskGroup() as tg:
        for device in getattr(plugin_manager.hook, async_hook_name)(
            config=config,
            cmdline_args=cmdline_args,
            device_manager=device_manager,
        ):
            tg.create_task(device)
    _LOGGER.debug("%s ran for %ss.", hook_name, time.monotonic() - start_time)


def _run_hook_sync(
    hook_name: str,
    plugin_manager: PluginManager,
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    device_manager: DeviceManager,
) -> None:
    start_time = time.monotonic()
    getattr(plugin_manager.hook, hook_name)(
        config=config,
        cmdline_args=cmdline_args,
        device_manager=device_manager,
    )
    _LOGGER.debug("%s ran for %ss.", hook_name, time.monotonic() - start_time)


async def _run_hook(
    hook_name: str,
    plugin_manager: PluginManager,
    config: BoardfarmConfig,
    cmdline_args: Namespace,
    device_manager: DeviceManager,
) -> None:
    if _is_async_hook_supported(hook_name=hook_name, device_manager=device_manager):
        await _run_hook_async(
            hook_name=hook_name,
            plugin_manager=plugin_manager,
            config=config,
            cmdline_args=cmdline_args,
            device_manager=device_manager,
        )
    else:
        _run_hook_sync(
            hook_name=hook_name,
            plugin_manager=plugin_manager,
            config=config,
            cmdline_args=cmdline_args,
            device_manager=device_manager,
        )


@hookimpl
async def boardfarm_setup_env(
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
        await _run_hook(
            hook_name="boardfarm_skip_boot",
            plugin_manager=plugin_manager,
            config=config,
            cmdline_args=cmdline_args,
            device_manager=device_manager,
        )
        return device_manager
    hooks = (
        "validate_device_requirements",
        "boardfarm_server_boot",
        "boardfarm_server_configure",
        "boardfarm_device_boot",
        "boardfarm_device_configure",
        "boardfarm_attached_device_boot",
        "boardfarm_attached_device_configure",
    )
    for hook in hooks:
        await _run_hook(
            hook_name=hook,
            plugin_manager=plugin_manager,
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
