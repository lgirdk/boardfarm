"""Boardfarm device manager."""

from typing import TypeVar

from pluggy import PluginManager

from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm3.exceptions import DeviceNotFound

T = TypeVar("T")  # pylint: disable=invalid-name
_DEVICE_MANAGER_INSTANCE = None


class DeviceManager:
    """Manages all the devices in the environment."""

    def __init__(self, plugin_manager: PluginManager) -> None:
        """Initialize device manager.

        :param plugin_manager: plugin manager
        """
        global _DEVICE_MANAGER_INSTANCE  # pylint: disable=global-statement
        if _DEVICE_MANAGER_INSTANCE is not None:
            raise ValueError("DeviceManager is already initialized.")
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
        raise DeviceNotFound(f"No device available of type {device_type}")

    def register_device(self, device: BoardfarmDevice) -> None:
        """Register a device as plugin with boardfarm.

        :param device: device instance to register
        """
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
        raise ValueError("DeviceManager is not instantiated.")
    return _DEVICE_MANAGER_INSTANCE
