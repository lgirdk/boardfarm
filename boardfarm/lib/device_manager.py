"""Boardfarm device manager."""

from typing import Dict, Type, TypeVar

from pluggy import PluginManager

from boardfarm.devices.base_devices import BoardfarmDevice
from boardfarm.exceptions import DeviceNotFound

T = TypeVar("T")  # pylint: disable=invalid-name


class DeviceManager:
    """Manages all the devices in the environment."""

    def __init__(self, plugin_manager: PluginManager) -> None:
        """Initialize device manager.

        :param plugin_manager: plugin manager
        """
        self._plugin_manager = plugin_manager

    def get_devices_by_type(self, device_type: Type[T]) -> Dict[str, T]:
        """Get devices of given type.

        :param device_type: device type
        :returns: devices of given type
        """
        return {
            name: plugin
            for name, plugin in self._plugin_manager.list_name_plugin()
            if isinstance(plugin, device_type)
        }

    def get_device_by_type(self, device_type: Type[T]) -> T:
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
