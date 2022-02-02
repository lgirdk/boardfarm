"""Boardfarm LAN device module."""

import logging

from boardfarm import hookimpl
from boardfarm.devices.base_devices import LinuxDevice
from boardfarm.templates.lan import LAN

_LOGGER = logging.getLogger(__name__)


class LinuxLAN(LinuxDevice, LAN):
    """Boardfarm LAN device."""

    @hookimpl
    def boardfarm_attached_device_boot(self) -> None:
        """Boardfarm hook implementation to boot LAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown LAN device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()
