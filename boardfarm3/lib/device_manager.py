"""Boardfarm device manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar
from unittest import mock

from boardfarm3.exceptions import DeviceNotFound, NotSupportedError

if TYPE_CHECKING:
    from pluggy import PluginManager

    from boardfarm3.devices.base_devices import BoardfarmDevice

T = TypeVar("T")  # pylint: disable=invalid-name
_DEVICE_MANAGER_INSTANCE: DeviceManager | None = None


def _get_attribute_with_ignore_exception(self: Any, __name: str) -> Any:  # noqa: ANN401
    try:
        return object.__getattribute__(self, __name)
    except (NotImplementedError, NotSupportedError):
        return None


class DeviceManager:
    """Manages all the devices in the environment."""

    def __init__(self, plugin_manager: PluginManager) -> None:
        """Initialize device manager.

        :param plugin_manager: plugin manager
        :raises ValueError: when DeviceManager is already initialized
        """
        global _DEVICE_MANAGER_INSTANCE  # pylint: disable=global-statement  # noqa: PLW0603
        if _DEVICE_MANAGER_INSTANCE is not None:
            msg = "DeviceManager is already initialized."  # type: ignore[unreachable]
            raise ValueError(msg)
        self._plugin_manager = plugin_manager
        _DEVICE_MANAGER_INSTANCE = self

    def get_devices_by_type(self, device_type: type[T]) -> dict[str, T]:
        """Get devices of given type.

        :param device_type: device type
        :returns: devices of given type
        """
        return {
            name: plugin
            for name, plugin in self._plugin_manager.list_name_plugin()
            if isinstance(plugin, device_type)
        }

    def get_device_by_type(self, device_type: type[T]) -> T:
        """Get first device of the given type.

        In order to get all devices of given type use get_devices_by_type.

        :param device_type: device type
        :returns: device of given type
        :raises DeviceNotFound: when device of given type not available
        """
        for _, plugin in self._plugin_manager.list_name_plugin():
            if isinstance(plugin, device_type):
                return plugin
        msg = f"No device available of type {device_type}"
        raise DeviceNotFound(msg)

    def register_device(self, device: BoardfarmDevice) -> None:
        """Register a device as plugin with boardfarm.

        :param device: device instance to register
        :type device: BoardfarmDevice
        """
        # During the registration of a plugin to the boardfarm, Pluggy calls all
        # of its properties. However, if a plugin has a method that throws an
        # exception, it can cause the boardfarm to crash. To address this issue
        # with Pluggy, we ignore the NotImplementedError and NotSupportedError
        # exceptions while registering a plugin.
        with mock.patch.object(
            device.__class__,
            "__getattribute__",
            _get_attribute_with_ignore_exception,
        ):
            self._plugin_manager.register(device, device.device_name)

    def unregister_device(self, device_name: str) -> None:
        """Unregister a device from boardfarm.

        :param device_name: name of device to unregister
        """
        self._plugin_manager.set_blocked(device_name)


def get_device_manager() -> DeviceManager:
    """Return device manager instance if already instantiated.

    When you run boardfarm it will initialize the DeviceManager.

    :raises ValueError: when device manager in not instantiated
    :return: device manager instance
    :rtype: DeviceManager
    """
    if _DEVICE_MANAGER_INSTANCE is None:
        msg = "DeviceManager is not instantiated."
        raise ValueError(msg)
    return _DEVICE_MANAGER_INSTANCE
