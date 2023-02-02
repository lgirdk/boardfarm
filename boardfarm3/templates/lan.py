"""Boardfarm LAN device template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from boardfarm3.lib.multicast import Multicast
    from boardfarm3.lib.networking import HTTPResult, IptablesFirewall

# pylint: disable=too-many-public-methods


class LAN(ABC):
    """Boardfarm LAN device template."""

    firewall: IptablesFirewall

    @property
    @abstractmethod
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT."""
        raise NotImplementedError

    @property
    @abstractmethod
    def lan_gateway(self) -> str:
        """Gateway address."""
        raise NotImplementedError

    @property
    @abstractmethod
    def http_proxy(self) -> str:
        """SOCKS5 dante proxy address, e.g http://{proxy_ip}:{proxy_port}/."""
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
    def start_ipv4_lan_client(
        self, wan_gw: Optional[Union[str, IPv4Address]] = None, prep_iface: bool = False
    ) -> str:
        """Restart ipv4 dhclient to obtain IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :param prep_iface: restart interface before dhclient request
        :return: IPv4 after renewal
        :raises pexpect.TimeoutException: in case of failure
        """
        raise NotImplementedError

    @abstractmethod
    def start_ipv6_lan_client(
        self, wan_gw: Optional[Union[str, IPv4Address]] = None, prep_iface: bool = False
    ) -> str:
        """Restart ipv6 dhclient to obtain IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :param prep_iface: restart interface before dhclient request
        :return: IPv6 after renewal
        :raises pexpect.TimeoutException: in case of failure
        """
        raise NotImplementedError

    @abstractmethod
    def set_link_state(self, interface: str, state: str) -> None:
        """Set link state.

        :param interface: interface name
        :param state: desired state
        """
        raise NotImplementedError

    @abstractmethod
    def is_link_up(
        self, interface: str, pattern: str = "BROADCAST,MULTICAST,UP"
    ) -> bool:
        """Return the link status.

        :param interface: interface name, defaults to "BROADCAST,MULTICAST,UP"
        :type interface: str
        :param pattern: interface state
        :type pattern: str, optional
        :return: True if the link is up
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_macaddr(self, interface: str) -> str:
        """Get the interface MAC address.

        :param interface: interface name
        :return: MAC address of the interface
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv4addr(self, interface: str) -> str:
        """Get ipv4 address of interface.

        :param interface: interface name
        :return: IPv4 address of the interface
        :raises BoardfarmException: in case IPv4 can not be found
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv6addr(self, interface: str) -> str:
        """Get ipv6 address of the interface.

        :param interface: interface name to get the link local
        :return: Global ipv6 address of the interface
        :raises BoardfarmException: in case ipv6 can not be found
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_link_local_ipv6addr(self, interface: str) -> str:
        """Get ipv6 link local address of the interface.

        :param interface: interface name
        :return: Link local ipv6 address of the interface
        :raises BoardfarmException: in case ipv6 can not be found
        """
        raise NotImplementedError

    @abstractmethod
    def ping(
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: Optional[str] = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> Union[bool, dict[str, Any]]:
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
    def get_default_gateway(self) -> IPv4Address:
        """Get the default gateway from ip route output.

        :return: IPv4 of the default gateway
        """
        raise NotImplementedError

    @abstractmethod
    def release_dhcp(self, interface: str) -> None:
        """Release ipv4 of the specified interface.

        :param interface: interface name
        """
        raise NotImplementedError

    @abstractmethod
    def renew_dhcp(self, interface: str) -> None:
        """Renew ipv4 of the specified interface by restart of the ipv4 dhclient.

        :param interface: interface name
        """
        raise NotImplementedError

    @abstractmethod
    def release_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Release ipv6 of the specified interface.

        :param interface: interface name
        :param stateless: run command with -S or -6 options. -6 by default
        """
        raise NotImplementedError

    @abstractmethod
    def renew_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Renew ipv6 of the specified interface.

        :param interface: interface name
        :param stateless: run command with -S or -6 options. -6 by default
        """
        raise NotImplementedError

    @contextmanager
    @abstractmethod
    def tcpdump_capture(
        self, fname: str, interface: str = "any", additional_args: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Capture packets from specified interface.

        Packet capture using tcpdump utility at a specified interface.

        :param fname: name of the file where packet captures will be stored
        :param interface: name of the interface, defaults to "any"
        :param additional_args: argument arguments to tcpdump executable
        :yield: process id of tcpdump process
        """
        raise NotImplementedError

    @abstractmethod
    def tshark_read_pcap(
        self,
        fname: str,
        additional_args: Optional[str] = None,
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
    def traceroute(
        self,
        host_ip: Union[str, IPv4Address],
        version: str = "",
        options: str = "",
        timeout: int = 60,
    ) -> Optional[str]:
        """Return output of traceroute command.

        :param host_ip: destination ip
        :param version: 4 or 6
        :param options: traceroute command options
        :param timeout: request timeout
        :return: traceroute command output
        """
        raise NotImplementedError

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
    def dns_lookup(self, domain_name: str) -> list[dict[str, Any]]:
        """Perform ``dig`` command in the devices to resolve DNS.

        :param domain_name: domain name which needs lookup
        :type domain_name: str
        :return: parsed dig command ouput
        :rtype: List[Dict[str, Any]]
        """
        raise NotImplementedError

    @abstractmethod
    def set_static_ip(
        self, interface: str, ip_address: IPv4Address, netmask: IPv4Address
    ) -> None:
        """Set given static ip for the LAN.

        :param interface: interface name
        :type interface: str
        :param ip_address: static ip address
        :type ip_address: IPv4Address
        :param netmask: netmask
        :type netmask: IPv4Address
        """
        raise NotImplementedError

    @abstractmethod
    def set_default_gw(self, ip_address: IPv4Address, interface: str) -> None:
        """Set given ip address as default gateway address for given interface.

        :param ip_address: gateway ip address
        :type ip_address: IPv4Address
        :param interface: interface name
        :type interface: str
        """
        raise NotImplementedError

    @abstractmethod
    def nmap(  # pylint: disable=too-many-arguments
        self,
        ipaddr: str,
        ip_type: str,
        port: Optional[Union[str, int]] = None,
        protocol: Optional[str] = None,
        max_retries: Optional[int] = None,
        min_rate: Optional[int] = None,
        opts: str = None,
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
