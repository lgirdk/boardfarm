"""Boardfarm Linux device module."""

import re
from argparse import Namespace
from ipaddress import IPv6Interface
from typing import Dict, List

import pexpect

from boardfarm.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm.exceptions import (
    ConfigurationFailure,
    EnvConfigError,
    SCPConnectionError,
)
from boardfarm.lib.boardfarm_pexpect import BoardfarmPexpect
from boardfarm.lib.connection_factory import connection_factory
from boardfarm.lib.connections.local_cmd import LocalCmd


class LinuxDevice(BoardfarmDevice):
    """Boardfarm Linux device."""

    _eth_interface = "eth1"
    _internet_access_cmd = ""

    def __init__(self, config: Dict, cmdline_args: Namespace) -> None:
        """Initialize linux device.

        :param config: device configuration
        :param cmdline_args: command line arguments
        """
        super().__init__(config, cmdline_args)
        self._console: BoardfarmPexpect = None
        self._shell_prompt = ["[\\w-]+@[\\w-]+:[\\w/~]+#"]

    def _connect(self) -> None:
        """Establish connection to the device via SSH."""
        if self._console is None:
            self._console = connection_factory(
                self._config.get("connection_type"),
                f"{self.device_name}.console",
                username=self._config.get("username"),
                password=self._config.get("password"),
                ip_addr=self._config.get("ipaddr"),
                port=self._config.get("port", "22"),
                shell_prompt=self._shell_prompt,
            )

    def _disconnect(self) -> None:
        """Disconnect SSH connection to the server."""
        if self._console is not None:
            self._console.close()
            self._console = None

    def get_interactive_consoles(self) -> Dict[str, BoardfarmPexpect]:
        """Get intractive consoles of the device.

        :returns: interactive consoles of the device
        """
        interactive_consoles = {}
        if self._console is not None:
            interactive_consoles["console"] = self._console
        return interactive_consoles

    def _get_nw_interface_ip_address(
        self, interface_name: str, is_ipv6: bool
    ) -> List[str]:
        """Get network interface ip address.

        :param interface_name: interface name
        :param is_ipv6: is ipv6 address
        :returns: IP address list
        """
        prefix = "inet" if not is_ipv6 else "inet6"
        ip_regex = prefix + r"\s(?:addr:)?\s*([^\s/]+)"
        output = self._console.execute_command(f"ifconfig {interface_name}")
        return re.findall(ip_regex, output)

    def _get_nw_interface_ipv4_address(self, network_interface: str) -> str:
        """Get IPv4 adddress of the given network interface.

        :param network_interface: network interface name
        :returns: IPv4 address of the given interface, None if not available
        """
        ipv4_address = None
        ips = self._get_nw_interface_ip_address(network_interface, False)
        if ips:
            ipv4_address = ips[0]
        return ipv4_address

    def _get_nw_interface_ipv6_address(
        self, network_interface: str, address_type: str = "global"
    ) -> str:
        """Get IPv6 address of the given network interface.

        :param network_interface: network interface name
        :param address_type: ipv6 address type. defaults to "global".
        :returns: IPv6 address of the given interface, None if not available
        """
        ipv6_address = None
        address_type = address_type.replace("-", "_")
        ip_addresses = self._get_nw_interface_ip_address(network_interface, True)
        for ip_addr in ip_addresses:
            if getattr(IPv6Interface(ip_addr), f"is_{address_type}"):
                ipv6_address = ip_addr
                break
        return ipv6_address

    def get_eth_interface_ipv4_address(self) -> str:
        """Get eth interface ipv4 address.

        :returns: IPv4 address of eth interface
        """
        return self._get_nw_interface_ipv4_address(self._eth_interface)

    def get_eth_interface_ipv6_address(self, address_type: str = "global") -> str:
        """Get IPv6 address of eth interface.

        :param address_type: ipv6 address type. defaults to "global".
        :returns: IPv6 address of eth interface
        """
        return self._get_nw_interface_ipv6_address(self._eth_interface, address_type)

    def scp_local_file_to_device(self, local_path: str, destination_path: str) -> None:
        """Copy a local file to a server using SCP.

        :param source: local file path
        :param destination: destination path
        :raises SCPConnectionError: when failed to perform SCP
        :raises EnvConfigError: when given password is None
        :raises SCPConnectionError: when SCP command return non-zero exit code
        """
        destination_path = (
            f"{self._config.get('username')}"
            f"@{self._config.get('ipaddr')}:{destination_path}"
        )
        args = [
            f"-P {self._config.get('port', '22')}",
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            "-o ServerAliveInterval=60",
            "-o ServerAliveCountMax=5",
            local_path,
            destination_path,
        ]
        session = LocalCmd(f"{self.device_name}.scp", "scp", args)
        session.setwinsize(24, 80)
        match_index = session.expect(
            [" password:", "\\d+%", pexpect.TIMEOUT, pexpect.EOF], timeout=20
        )
        if match_index in (2, 3):
            raise SCPConnectionError(
                f"Failed to perform SCP from {local_path} to {destination_path}"
            )
        if match_index == 0:
            password = self._config.get("password", None)
            if password is not None:
                session.sendline(password)
            else:
                raise EnvConfigError("Password shouldn't be None")
        session.expect(pexpect.EOF, timeout=90)
        if session.wait() != 0:
            raise SCPConnectionError(
                f"Failed to SCP file from {local_path} to {destination_path}"
            )

    def download_file_from_uri(self, file_uri: str, destination_dir: str) -> str:
        """Download(wget) file from given URI.

        :param file_uri: file uri location
        :param destination_dir: destination directory
        :returns: downloaded file name
        :raises ConfigurationFailure: when file download failed from given URI
        """
        file_name = file_uri.split("/")[-1]
        file_path = f"{destination_dir}/{file_name}"
        if " saved [" not in self._console.execute_command(
            f"{self._internet_access_cmd} wget '{file_uri}' -O {file_path}"
        ):
            raise ConfigurationFailure(f"Failed to download image from {file_uri}")
        return file_name
