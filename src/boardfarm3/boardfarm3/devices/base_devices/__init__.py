"""Boardfarm base devices package."""

from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.devices.base_devices.linux_device import LinuxDevice

__all__ = ["BoardfarmDevice", "LinuxDevice"]
