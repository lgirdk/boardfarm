"""Boardfarm WAN device template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from ipaddress import IPv4Address

    from boardfarm3.lib.multicast import Multicast
    from boardfarm3.lib.networking import HTTPResult, IptablesFirewall

# pylint: disable=duplicate-code,too-many-public-methods


class WAN(ABC):
    """Boardfarm WAN device template."""

    firewall: IptablesFirewall

    @property
    @abstractmethod
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT."""
        raise NotImplementedError

    @property
    @abstractmethod
    def multicast(self) -> Multicast:
        """Return multicast component instance.

        :return: multicast component instance
        :rtype: Multicast
        """
        raise NotImplementedError

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
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv6addr(self, interface: str) -> str:
        """Return ipv4 address of the interface.

        :param interface: interface name
        :return: IPv6 of the interface
        :raises BoardfarmException: in case IPv6 is not found
        """
        raise NotImplementedError

    @abstractmethod
    def is_link_up(
        self,
        interface: str,
        pattern: str = "BROADCAST,MULTICAST,UP",
    ) -> bool:
        """Return the link status.

        :param interface: interface name, defaults to "BROADCAST,MULTICAST,UP"
        :type interface: str
        :param pattern: interface state
        :type pattern: str
        :return: True if the link is up
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def ping(  # noqa: PLR0913
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: str | None = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> bool | dict:
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
        raise NotImplementedError

    @abstractmethod
    def curl(
        self,
        url: str | IPv4Address,
        protocol: str,
        port: str | int | None = None,
        options: str = "",
    ) -> bool:
        """Perform curl action to web service.

        :param url : web service address
        :param protocol : Web Protocol (http or https)
        :param port : port number of server
        :param options : Additional curl options
        """
        raise NotImplementedError

    @abstractmethod
    def start_http_service(self, port: str, ip_version: str) -> str:
        """Start HTTP service on given port number.

        :param port: port number
        :param ip_version: ip version, 4 - IPv4, 6 - IPv6
        :return: pid number of the http service
        """
        raise NotImplementedError

    @abstractmethod
    def stop_http_service(self, port: str) -> None:
        """Stop http service running on given port.

        :param port: port number
        """
        raise NotImplementedError

    @abstractmethod
    def http_get(self, url: str, timeout: int) -> HTTPResult:
        """Peform http get and return parsed result.

        :param url: url to get the response
        :type url: str
        :param timeout: connection timeout for the curl command in seconds
        :type timeout: int
        :return: parsed http response
        :rtype: HTTPResult
        """
        raise NotImplementedError

    @abstractmethod
    def tshark_read_pcap(
        self,
        fname: str,
        additional_args: str | None = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file.

        :param fname: name of the file in which captures are saved
        :param additional_args: additional arguments for tshark command
        :param timeout: time out for tshark command to be executed, defaults to 30
        :param rm_pcap: If True remove the packet capture file after reading it
        :return: return tshark read command console output
        """
        raise NotImplementedError

    @abstractmethod
    def dns_lookup(self, domain_name: str) -> list[dict[str, Any]]:
        """Perform ``dig`` command in the devices to resolve DNS.

        :param domain_name: domain name which needs lookup
        :type domain_name: str
        :return: parsed dig command ouput
        :rtype: List[Dict[str, Any]]
        """
        raise NotImplementedError

    @abstractmethod
    def nmap(  # pylint: disable=too-many-arguments  # noqa: PLR0913
        self,
        ipaddr: str,
        ip_type: str,
        port: str | int | None = None,
        protocol: str | None = None,
        max_retries: int | None = None,
        min_rate: int | None = None,
        opts: str | None = None,
    ) -> dict:
        """Perform nmap operation on linux device.

        :param ipaddr: ip address on which nmap is performed
        :type ipaddr: str
        :param ip_type: type of ip eg: ipv4/ipv6
        :type ip_type: str
        :param port: destination port on ip, defaults to None
        :type port: Optional[Union[str, int]], optional
        :param protocol: specific protocol to follow eg: tcp(-sT)/udp(-sU),
            defaults to None
        :type protocol: Optional[str], optional
        :param max_retries: number of port scan probe retransmissions, defaults to None
        :type max_retries: Optional[int], optional
        :param min_rate: Send packets no slower than per second, defaults to None
        :type min_rate: Optional[int], optional
        :param opts: other options for a nmap command, defaults to None
        :type opts: str, optional
        :raises BoardfarmException: Raises exception if ip type is invalid
        :return: response of nmap command in xml/dict format
        :rtype: dict
        """
        raise NotImplementedError

    @contextmanager
    @abstractmethod
    def tcpdump_capture(
        self,
        fname: str,
        interface: str = "any",
        additional_args: str | None = None,
    ) -> Generator[str, None, None]:
        """Capture packets from specified interface.

        Packet capture using tcpdump utility at a specified interface.

        :param fname: name of the file where packet captures will be stored
        :param interface: name of the interface, defaults to "any"
        :param additional_args: argument arguments to tcpdump executable
        :yield: process id of tcpdump process
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def rssh_username(self) -> str:
        """Return the WAN username for reverse SSH.

        :return: WAN username
        :rtype: str
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def rssh_password(self) -> str:
        """Return the WAN password for reverse SSH.

        :return: WAN password
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def is_connect_to_board_via_reverse_ssh_successful(
        self,
        rssh_username: str,
        rssh_password: str | None,
        reverse_ssh_port: str,
    ) -> bool:
        """Perform reverse SSH from jump server to CPE.

        :param rssh_username: username of the cpe
        :type rssh_username: str
        :param rssh_password: password to connect
        :type rssh_password: Optional[str]
        :param reverse_ssh_port: the port number
        :type reverse_ssh_port: str
        :return: True if the RSSH is successful, false otherwise
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def get_network_statistics(
        self,
    ) -> dict[str, Any] | list[dict[str, Any]] | Iterator[dict[str, Any]]:
        """Execute netstat command to get the port status.

        :return: parsed output of netstat command
        :rtype: Union[dict[str, Any], list[dict[str, Any]], Iterator[dict[str, Any]]]
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_macaddr(self, interface: str) -> str:
        """Get the interface MAC address.

        :param interface: interface name
        :type interface: str
        :return: mac address of the interface
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_mask(self, interface: str) -> str:
        """Get the subnet mask of the interface.

        :param interface: name of the interface
        :type interface: str
        :return: subnet mask of interface
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_mtu_size(self, interface: str) -> int:
        """Get the MTU size of the interface in bytes.

        :param interface: name of the interface
        :type interface: str
        :return: size of the MTU in bytes
        :rtype: int
        """
        raise NotImplementedError

    @abstractmethod
    def add_route(self, destination: str, gw_interface: str) -> None:
        """Add a route to a destination via a specific gateway interface.

        The method will internally calculate the exit interface's ip address
        before adding the route.
        The gw_interface must be an interface name that exists on the host.

        :param destination: ip address of the destination
        :type destination: str
        :param gw_interface: name of the interface
        :type gw_interface: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_route(self, destination: str) -> None:
        """Delete a route to a destination.

        :param destination: ip address of the destination
        :type destination: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        """
        raise NotImplementedError
