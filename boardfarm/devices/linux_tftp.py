"""Boardfarm Linux TFTP device module."""

import logging

from boardfarm import hookimpl
from boardfarm.devices.base_devices import LinuxDevice
from boardfarm.lib.device_manager import DeviceManager
from boardfarm.templates.tftp import TFTP

_LOGGER = logging.getLogger(__name__)


class LinuxTFTP(LinuxDevice, TFTP):
    """Boardfarm Linux TFTP device."""

    _tftpboot_dir = "/tftpboot"
    _internet_access_cmd = "mgmt"

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot TFTP device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    def boardfarm_post_deploy_devices(self, device_manager: DeviceManager) -> None:
        """Boardfarm hook implementation to shutdown TFTP device.

        :param device_manager: device manager instance
        """
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()
        device_manager.unregister_device(self.device_name)

    def download_image_from_uri(self, image_uri: str) -> str:
        """Download image from given URI.

        :param image_uri: image file URI
        :returns: downloaded image name
        """
        return self.download_file_from_uri(image_uri, self._tftpboot_dir)
