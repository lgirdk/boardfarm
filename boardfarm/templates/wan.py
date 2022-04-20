"""Boardfarm WAN device template."""

from abc import ABC, abstractmethod
from ipaddress import IPv4Address
from typing import Optional, Union


class WAN(ABC):
    """Boardfarm WAN device template."""

    @property
    @abstractmethod
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT."""

    @abstractmethod
    def copy_local_file_to_tftpboot(self, local_file_path: str) -> str:
        """SCP local file to tftpboot directory.

        :param local_file_path: local file path
        """
        raise NotImplementedError

    @abstractmethod
    def download_image_to_tftpboot(self, image_uri: str) -> str:
        """Download image from URL to tftpboot directory.

        :param image_uri: image file URI
        :returns: name of the image in tftpboot
        """
        raise NotImplementedError

    @abstractmethod
    def get_eth_interface_ipv4_address(self) -> str:
        """Get eth interface ipv4 address.

        :returns: IPv4 address of eth interface
        """
        raise NotImplementedError

    @abstractmethod
    def get_eth_interface_ipv6_address(self, address_type: str = "global") -> str:
        """Get IPv6 address of eth interface.

        :param address_type: ipv6 address type. defaults to "global".
        :returns: IPv6 address of eth interface
        """
        raise NotImplementedError

    @abstractmethod
    def execute_snmp_command(self, snmp_command: str) -> str:
        """Execute SNMP command.

        :param snmp_command: snmp command
        :returns: given snmp command output
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv4addr(self, interface: str) -> str:
        """Return ipv4 address of the interface.

        :param interface: interface name
        :return: IPv4 of the interface
        :raises BoardfarmException: in case IPv4 is not found
        """

    @abstractmethod
    def get_interface_ipv6addr(self, interface: str) -> str:
        """Return ipv4 address of the interface.

        :param interface: interface name
        :return: IPv6 of the interface
        :raises BoardfarmException: in case IPv6 is not found
        """

    @abstractmethod
    def ping(
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: Optional[str] = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> Union[bool, dict]:
        """Ping remote host.

        Return True if ping has 0% loss
        or parsed output in JSON if json_output=True flag is provided.

        :param ping_ip: ping ip
        :param ping_count: number of ping, defaults to 4
        :param ping_interface: ping via interface, defaults to None
        :param options: extra ping options, defaults to ""
        :param timeout: timeout, defaults to 50
        :param json_output: return ping output in dictionary format, defaults to False
        :return: ping output
        """

    @abstractmethod
    def curl(
        self,
        url: Union[str, IPv4Address],
        protocol: str,
        port: Optional[Union[str, int]] = None,
        options: str = "",
    ) -> bool:
        """Perform curl action to web service.

        :param url : web service address
        :param protocol : Web Protocol (http or https)
        :param port : port number of server
        :param options : Additional curl options
        """
