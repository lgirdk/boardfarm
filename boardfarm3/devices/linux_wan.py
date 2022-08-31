"""Boardfarm WAN device module."""

import logging

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.templates.wan import WAN

_LOGGER = logging.getLogger(__name__)


class LinuxWAN(LinuxDevice, WAN):
    """Boardfarm WAN device."""

    _tftpboot_dir = "/tftpboot"

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot WAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown WAN device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    @property
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT."""
        return self.eth_interface

    def copy_local_file_to_tftpboot(self, local_file_path: str) -> None:
        """SCP local file to tftpboot directory.

        :param local_file_path: local file path
        """
        self.scp_local_file_to_device(local_file_path, self._tftpboot_dir)

    def download_image_to_tftpboot(self, image_uri: str) -> str:
        """Download image from URL to tftpboot directory.

        :param image_uri: image file URI
        :returns: name of the image in tftpboot
        """
        return self.download_file_from_uri(image_uri, self._tftpboot_dir)

    def execute_snmp_command(self, snmp_command: str) -> str:
        """Execute snmp command.

        :param snmp_command: snmp command
        :returns: snmp command output
        :raises ValueError: when snmp command is invalid
        """
        # Only allowing snmp commands to be executed from wan
        # only wan has snmp utils installed on it.
        if not snmp_command.startswith("snmp"):
            raise ValueError(f"'{snmp_command}' is not a SNMP command")
        return self._console.execute_command(snmp_command)
