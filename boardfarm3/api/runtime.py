"""Per-process boardfarm runtime owned by the API agent."""

from __future__ import annotations

import asyncio
from argparse import Namespace
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pluggy import PluginManager

from boardfarm3 import PROJECT_NAME
from boardfarm3.api import plugin as api_plugin
from boardfarm3.plugins.hookspecs import core as core_hookspecs

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_config import BoardfarmConfig
    from boardfarm3.lib.device_manager import DeviceManager

API_ENTRY_POINT_GROUP = "boardfarm_api"


@dataclass
# pylint: disable-next=too-many-instance-attributes
class RuntimeOptions:
    """Options controlling a single boardfarm runtime."""

    board_name: str
    skip_boot: bool = False
    legacy: bool = False
    skip_contingency_checks: bool = False
    save_console_logs: str = ""
    ignore_devices: str = ""
    quiet_after: float = 600.0
    plugin_args: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeContext:
    """Owns the plugin manager, config and devices for one board."""

    options: RuntimeOptions
    plugin_manager: PluginManager = field(init=False)
    cmdline_args: Namespace = field(init=False)
    config: BoardfarmConfig | None = field(init=False, default=None)
    device_manager: DeviceManager | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Bootstrap the plugin manager and synthesise command line arguments."""
        self.plugin_manager = self._build_plugin_manager()
        self.cmdline_args = self._build_cmdline_args()

    @staticmethod
    def _build_plugin_manager() -> PluginManager:
        """Build a plugin manager with both entry-point groups loaded.

        :return: plugin manager
        :rtype: PluginManager
        """
        plugin_manager = PluginManager(PROJECT_NAME)
        plugin_manager.add_hookspecs(core_hookspecs)
        plugin_manager.load_setuptools_entrypoints(PROJECT_NAME)
        plugin_manager.load_setuptools_entrypoints(API_ENTRY_POINT_GROUP)
        if not plugin_manager.is_registered(api_plugin):
            plugin_manager.register(api_plugin, "core_api")
        plugin_manager.hook.boardfarm_add_hookspecs(plugin_manager=plugin_manager)
        return plugin_manager

    def _build_cmdline_args(self) -> Namespace:
        """Synthesise the Namespace that device constructors expect.

        Device classes read ``board_name``, ``legacy``, ``skip_boot``,
        ``skip_contingency_checks``, ``save_console_logs``, ``ignore_devices``
        and ``inventory_config`` off this object.

        :return: command line arguments
        :rtype: Namespace
        """
        return Namespace(
            board_name=self.options.board_name,
            legacy=self.options.legacy,
            skip_boot=self.options.skip_boot,
            skip_contingency_checks=self.options.skip_contingency_checks,
            save_console_logs=self.options.save_console_logs,
            ignore_devices=self.options.ignore_devices,
            inventory_config="",
            env_config="",
            # lgi-shared plugin args — defaults match what argparse produces when
            # no flag is passed; can be overridden via options.plugin_args
            flash_image=None,
            flash_strategy=None,
            flash_sku=None,
            dependent_image=None,
            dependent_strategy="bootloader",
            # any plugin-specific args passed in the session options
            **self.options.plugin_args,
        )

    def refresh_cmdline_args(self) -> None:
        """Rebuild the synthesised Namespace after options change.

        ``cmdline_args`` is built once at construction, so any option applied
        later (``legacy``, ``skip_boot``, ...) must be re-materialised before
        devices are constructed, or it is silently ignored.
        """
        self.cmdline_args = self._build_cmdline_args()

    def resolve(self, payload: dict[str, Any]) -> BoardfarmConfig:
        """Resolve an opaque payload into a BoardfarmConfig.

        :param payload: opaque session payload
        :type payload: dict[str, Any]
        :return: parsed boardfarm config
        :rtype: BoardfarmConfig
        """
        config: BoardfarmConfig = self.plugin_manager.hook.boardfarm_api_resolve_config(
            payload=payload,
            cmdline_args=self.cmdline_args,
            plugin_manager=self.plugin_manager,
        )
        self.config = config
        return config

    def register_devices(self) -> DeviceManager:
        """Register every device from the resolved config.

        :raises RuntimeError: when called before ``resolve()``
        :return: device manager with all registered devices
        :rtype: DeviceManager
        """
        if self.config is None:
            msg = "resolve() must be called before register_devices()"
            raise RuntimeError(msg)
        device_manager: DeviceManager = (
            self.plugin_manager.hook.boardfarm_register_devices(
                config=self.config,
                cmdline_args=self.cmdline_args,
                plugin_manager=self.plugin_manager,
            )
        )
        self.device_manager = device_manager
        return device_manager

    async def boot(self) -> None:
        """Run the boardfarm boot and configure chain.

        :raises RuntimeError: when called before ``register_devices()``
        """
        if self.config is None or self.device_manager is None:
            msg = "register_devices() must be called before boot()"
            raise RuntimeError(msg)
        await self.plugin_manager.hook.boardfarm_setup_env(
            config=self.config,
            cmdline_args=self.cmdline_args,
            plugin_manager=self.plugin_manager,
            device_manager=self.device_manager,
        )

    def release(self, deployment_status: dict[str, Any]) -> None:
        """Release all devices, shutting their connections down cleanly.

        :param deployment_status: outcome of the deployment
        :type deployment_status: dict[str, Any]
        """
        if self.config is None or self.device_manager is None:
            return
        self.plugin_manager.hook.boardfarm_release_devices(
            config=self.config,
            cmdline_args=self.cmdline_args,
            plugin_manager=self.plugin_manager,
            deployment_status=deployment_status,
            device_manager=self.device_manager,
        )

    def boot_blocking(self) -> None:
        """Run ``boot()`` to completion on the calling thread.

        This is the callable submitted to the single worker thread; boardfarm's
        boot chain uses ``asyncio.TaskGroup`` internally, which requires its own
        event loop.
        """
        asyncio.run(self.boot())
