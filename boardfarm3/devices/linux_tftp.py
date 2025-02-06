"""Boardfarm Linux TFTP device module."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from ipaddress import IPv4Address

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import ConfigurationFailure, DeviceBootFailure
from boardfarm3.lib.device_manager import DeviceManager
from boardfarm3.templates.tftp import TFTP

_LOGGER = logging.getLogger(__name__)


class LinuxTFTP(LinuxDevice, TFTP):
    """Boardfarm Linux LAN side TFTP device.

    This is a disposable device that can be used when a LAN side tftp server
    is needed. I.e. for some CPEs flashing via bootloader requires a LAN side
    tftp device. This device is disconnected on post deploy.
    """

    _tftpboot_dir = "/tftpboot"
    _internet_access_cmd = "mgmt"
    # This value will be updated on every LinuxTFTP device boot
    # to make sure every LinuxTFTP device has a unique static ip address
    _last_static_ip_address = IPv4Address("192.168.1.10")

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot TFTP device.

        :raises DeviceBootFailure: if tftpd fails to start
        """
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        # TODO: to be cleaned up once Docker factory comes into place
        self._set_eth_interface_ipv4_address(LinuxTFTP._last_static_ip_address)
        LinuxTFTP._last_static_ip_address += 1
        if "Restarting" not in self._console.execute_command(
            "/etc/init.d/tftpd-hpa restart",
        ):
            msg = "Failed to restart tftpd-hpa"
            raise DeviceBootFailure(msg)
        if "in.tftpd is running" not in self._console.execute_command(
            "/etc/init.d/tftpd-hpa status",
        ):
            msg = "Failed tftpd-hpa not running"
            raise DeviceBootFailure(msg)

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm hook implementation to initialize TFTP device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    async def boardfarm_skip_boot_async(self) -> None:
        """Boardfarm hook implementation to initialize TFTP device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        await self._connect_async()

    @hookimpl
    def boardfarm_post_deploy_devices(self, device_manager: DeviceManager) -> None:
        """Boardfarm hook implementation to shutdown TFTP device.

        :param device_manager: device manager instance
        :type device_manager: DeviceManager
        """
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._console.execute_command("/etc/init.d/tftpd-hpa stop")
        self._disconnect()
        device_manager.unregister_device(self.device_name)

    def download_image_from_uri(self, image_uri: str) -> str:
        """Download image from given URI.

        :param image_uri: image file URI
        :type image_uri: str
        :returns: downloaded image name
        :rtype: str
        """
        return self.download_file_from_uri(image_uri, self._tftpboot_dir)

    def _set_eth_interface_ipv4_address(self, static_ip: IPv4Address) -> None:
        """Set a static IPv4 on the DUT connected interface.

        :param static_ip: static ipv4 address
        :type static_ip: IPv4Address
        :raises ConfigurationFailure: On failed to set given static ip
        """
        self._console.execute_command(
            f"ifconfig {self.eth_interface} {static_ip} netmask 255.255.255.0 up",
        )
        if str(static_ip) != self._get_nw_interface_ipv4_address(self.eth_interface):
            msg = f"Failed to configure {self.eth_interface} with {static_ip}"
            raise ConfigurationFailure(
                msg,
            )

    @contextmanager
    def set_tmp_static_ip(
        self, static_address: IPv4Address
    ) -> Generator[None, None, None]:
        """Temporarily set a static IPv4 on the DUT connected iface via the `ip` cmd.

        :param static_address: Static IPv4 address to be set
        :type static_address: IPv4Address
        :yield: The DUT connected interface with the static ip address applied
        :rtype: Generator[None, None, None]
        """
        self._console.execute_command(f"ip a flush dev {self.eth_interface}")
        self._console.execute_command(
            f"ip a add {static_address}/32 dev {self.eth_interface}",
        )
        self._console.execute_command(f"ip link set {self.eth_interface} up")
        self._console.execute_command("ip route del default")
        self._console.execute_command(
            f"ip route add default via {static_address} dev {self.eth_interface}"
        )
        self._console.execute_command("ip a")
        yield
        self._console.execute_command("ip route del default")
        self._console.execute_command(f"ip a flush dev {self.eth_interface}")

    def restart_lighttpd(self) -> None:
        """Restart lighttpd service."""
        self._console.execute_command("service lighttpd restart")

    def stop_lighttpd(self) -> None:
        """Stop the lighttpd service."""
        self._console.execute_command("service lighttpd stop")
