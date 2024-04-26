"""Boardfarm LAN device template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Generator
    from ipaddress import IPv4Address

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.multicast import Multicast
    from boardfarm3.lib.networking import (
        HTTPResult,
        IptablesFirewall,
        NSLookup,
    )

# pylint: disable=too-many-public-methods,duplicate-code


class LAN(ABC):
    """Boardfarm LAN device template."""

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

    @property
    @abstractmethod
    def console(self) -> BoardfarmPexpect:
        """Returns LAN console.

        :return: console
        :rtype: BoardfarmPexpect
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def firewall(self) -> IptablesFirewall:
        """Returns Firewall iptables instance.

        :return: firewall iptables instance with console object
        :rtype: IptablesFirewall
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def nslookup(self) -> NSLookup:
        """Returns NSLookup utility instance.

        :return: nslookup utility instance with console object
        :rtype: NSLookup
        """
        raise NotImplementedError

    @abstractmethod
    def start_ipv4_lan_client(
        self,
        wan_gw: str | IPv4Address | None = None,
        prep_iface: bool = False,
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
        self,
        wan_gw: str | IPv4Address | None = None,
        prep_iface: bool = False,
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

        :param interface: name of the interface
        :type interface: str
        :param state: desired state up or down
        :type state: str
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
    def get_interface_mask(self, interface: str) -> str:
        """Get the subnet mask of the interface.

        :param interface: name of the interface
        :type interface: str
        :return: subnet mask of interface
        :rtype: str
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
    ) -> bool | dict[str, Any]:
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
    def traceroute(
        self,
        host_ip: str | IPv4Address,
        version: str = "",
        options: str = "",
        timeout: int = 60,
    ) -> str | None:
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
    def dns_lookup(self, domain_name: str, record_type: str) -> list[dict[str, Any]]:
        """Perform ``dig`` command in the devices to resolve DNS.

        :param domain_name: domain name which needs lookup
        :type domain_name: str
        :param record_type: AAAA for ipv6 else A
        :type record_type: str
        :return: parsed dig command ouput
        :rtype: List[Dict[str, Any]]
        """
        raise NotImplementedError

    @abstractmethod
    def set_static_ip(
        self,
        interface: str,
        ip_address: IPv4Address,
        netmask: IPv4Address,
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

    @abstractmethod
    def enable_ipv6(self) -> None:
        """Enable ipv6 on the connected client interface."""
        raise NotImplementedError

    @abstractmethod
    def disable_ipv6(self) -> None:
        """Disable ipv6 on the connected client interface."""
        raise NotImplementedError

    @abstractmethod
    def create_upnp_rule(self, int_port: str, ext_port: str, protocol: str) -> str:
        """Create UPnP rule on the device.

        :param int_port: internal port for upnp
        :type int_port: str
        :param ext_port: external port for upnp
        :type ext_port: str
        :param protocol: protocol to be used
        :type protocol: str
        :return: output of upnpc add port command
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_upnp_rule(self, ext_port: str, protocol: str) -> str:
        """Delete UPnP rule on the device.

        :param ext_port: external port for upnp
        :type ext_port: str
        :param protocol: protocol to be used
        :type protocol: str
        :return: output of upnpc delete port command
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
    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        """
        raise NotImplementedError

    @abstractmethod
    def perform_scp(
        self,
        source: str,
        destination: str,
        action: Literal["download", "upload"] = "download",
    ) -> None:
        """Perform SCP from linux device.

        :param source: source file path
        :type source: str
        :param destination: destination file path
        :type destination: str
        :param action: scp action(download/upload), defaults to "download"
        :type action: Literal["download", "upload"], optional
        """
        raise NotImplementedError

    @abstractmethod
    def start_traffic_receiver(
        self,
        traffic_port: int,
        bind_to_ip: str | None = None,
        ip_version: int | None = None,
    ) -> int | bool:
        """Start the server on a linux device to generate traffic using iperf3.

        :param traffic_port: server port to listen on
        :type traffic_port: int
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to None
        :type bind_to_ip: str, optional
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int, optional
        :return: the process id(pid) or False if pid could not be generated
        :rtype: int | bool
        """
        raise NotImplementedError

    @abstractmethod
    def start_traffic_sender(  # pylint: disable=too-many-arguments  # noqa: PLR0913
        self,
        host: str,
        traffic_port: int,
        bandwidth: int | None = None,
        bind_to_ip: str | None = None,
        direction: str | None = None,
        ip_version: int | None = None,
        udp_protocol: bool = False,
        time: int = 10,
    ) -> int | bool:
        """Start traffic on a linux client using iperf3.

        :param host: a host to run in client mode
        :type host: str
        :param traffic_port: server port to connect to
        :type traffic_port: int
        :param bandwidth: bandwidth(mbps) at which the traffic
            has to be generated, defaults to None
        :type bandwidth: Optional[int], optional
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to None
        :type bind_to_ip: Optional[str], optional
        :param direction: `--reverse` to run in reverse mode
            (server sends, client receives) or `--bidir` to run in
            bidirectional mode, defaults to None
        :type direction: Optional[str], optional
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int, optional
        :param udp_protocol: use UDP rather than TCP, defaults to False
        :type udp_protocol: bool
        :param time: time in seconds to transmit for, defaults to 10
        :type time: int
        :return: the process id(pid) or False if pid could not be generated
        :rtype: int | bool
        """
        raise NotImplementedError
