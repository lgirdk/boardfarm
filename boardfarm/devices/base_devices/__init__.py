"""Boardfarm base devices package."""

from boardfarm.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm.devices.base_devices.linux_device import LinuxDevice

__all__ = ["BoardfarmDevice", "LinuxDevice"]
