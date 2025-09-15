"""Boardfarm WAN device template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from ipaddress import IPv4Address

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.multicast import Multicast
    from boardfarm3.lib.network_utils import NetworkUtility
    from boardfarm3.lib.networking import HTTPResult, IptablesFirewall, NSLookup


# pylint: disable=duplicate-code,too-many-public-methods


class WAN(ABC):
    """Boardfarm WAN device template."""

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

    @property
    @abstractmethod
    def console(self) -> BoardfarmPexpect:
        """Returns WAN console.

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
    def nw_utility(self) -> NetworkUtility:
        """Returns Network utility instance.

        :return: network utiluty instance with console object
        :rtype: NetworkUtility
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

    @property
    @abstractmethod
    def http_proxy(self) -> str:
        """SOCKS5 Dante proxy address, e.g http://{proxy_ip}:{proxy_port}/."""
        raise NotImplementedError

    @cached_property
    @abstractmethod
    def ipv4_addr(self) -> str:
        """Return the IPv4 address on IFACE facing DUT.

        :return: IPv4 address in string format.
        :rtype: str
        """
        raise NotImplementedError

    @cached_property
    @abstractmethod
    def ipv6_addr(self) -> str:
        """Return the IPv6 address on IFACE facing DUT.

        :return: IPv6 address in string format.
        :rtype: str
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
    def execute_snmp_command(self, snmp_command: str, timeout: int = 30) -> str:
        """Execute SNMP command.

        :param snmp_command: snmp command
        :type snmp_command: str
        :param timeout: pexpect timeout for the command in seconds, defaults to 30
        :type timeout: int
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
    def http_get(self, url: str, timeout: int, options: str) -> HTTPResult:
        """Peform http get and return parsed result.

        :param url: url to get the response
        :type url: str
        :param timeout: connection timeout for the curl command in seconds
        :type timeout: int
        :param options: additional curl options
        :type options: str
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
    def dns_lookup(
        self, domain_name: str, record_type: str, opts: str = ""
    ) -> list[dict[str, Any]]:
        """Perform ``dig`` command in the devices to resolve DNS.

        :param domain_name: domain name which needs lookup
        :type domain_name: str
        :param record_type: AAAA for ipv6 else A
        :type record_type: str
        :param opts: options to be provided to dig command, defaults to ""
        :type opts: str
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
        timeout: int = 30,
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
        :param timeout: pexpect timeout for the command in seconds, defaults to 30
        :type timeout: int
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
    ) -> Generator[str]:
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

    @abstractmethod
    def scp_device_file_to_local(self, local_path: str, source_path: str) -> None:
        """Copy a local file from a server using SCP.

        :param local_path: local file path
        :param source_path: source path
        """
        raise NotImplementedError

    @abstractmethod
    def start_traffic_receiver(
        self,
        traffic_port: int,
        bind_to_ip: str | None = None,
        ip_version: int | None = None,
        udp_only: bool | None = None,
    ) -> tuple[int, str]:
        """Start the server on a linux device to generate traffic using iperf3.

        :param traffic_port: server port to listen on
        :type traffic_port: int
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to None
        :type bind_to_ip: str, optional
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int,
        :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
        :type udp_only: bool, optional
        :raises CodeError: raises if unable to start server
        :return: the process id(pid) and log file path
        :rtype: tuple[int, str]
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
        client_port: int | None = None,
        udp_only: bool | None = None,
    ) -> tuple[int, str]:
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
        :param client_port: client port from where the traffic is getting started
        :type client_port: int | None
        :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
        :type udp_only: bool, optional
        :raises CodeError: raises if unable to start server
        :return: the process id(pid) and log file path
        :rtype: tuple[int, str]
        """
        raise NotImplementedError

    @abstractmethod
    def stop_traffic(self, pid: int | None = None) -> bool:
        """Stop the iPerf3 process for a specific PID or killall.

        :param pid: process ID for a iPerf3 service either for reciever or sender,
            defaults to None
        :type pid: int | None
        :return: True if process is stopped else False
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def get_iperf_logs(self, log_file: str) -> str:
        """Read the file output for traffic flow.

        :param log_file: iperf log file path
        :type log_file: str
        :return: traffic flow logs
        :rtype: str
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
    def get_date(self) -> str | None:
        """Get the system date and time.

        .. code-block:: python

            # example output
            donderdag, mei 23, 2024 14:23:39


        :return: date
        :rtype: str | None
        """
        raise NotImplementedError

    @abstractmethod
    def set_date(self, opt: str, date_string: str) -> bool:
        """Set the device's date and time.

        :param date_string: value to be changed
        :type date_string: str
        :param opt: Option to set the date or time or day
        :type opt: str
        :return: True if set is successful
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def release_dhcp(self, interface: str) -> None:
        """Release IPv4 of the specified interface.

        :param interface: interface name
        :type interface: str
        """
        raise NotImplementedError

    @abstractmethod
    def set_static_ip(
        self,
        interface: str,
        ip_address: IPv4Address,
        netmask: IPv4Address,
    ) -> None:
        """Set given static IP for the LAN.

        :param interface: interface name
        :type interface: str
        :param ip_address: static IP address
        :type ip_address: IPv4Address
        :param netmask: netmask
        :type netmask: IPv4Address
        """
        raise NotImplementedError

    @abstractmethod
    def set_default_gw(self, ip_address: IPv4Address, interface: str) -> None:
        """Set given IP address as default gateway address for given interface.

        :param ip_address: gateway IP address
        :type ip_address: IPv4Address
        :param interface: interface name
        :type interface: str
        """
        raise NotImplementedError

    @abstractmethod
    def hping_flood(
        self,
        protocol: str,
        target: str,
        packet_count: str,
        extra_args: str | None = None,
        pkt_interval: str = "",
    ) -> str:
        """Validate SYN, UDP and ICMP flood operation.

        :param protocol: mode, for ex 'S': syn-flood '1': ping-flood (icmp) '2': udp
        :type protocol: str
        :param target: target IP addr
        :type target: str
        :param packet_count: number of packets to be transmitted.
        :type packet_count: str
        :param extra_args: extra arguments to be passed, defaults to None
        :type extra_args: str
        :param pkt_interval: wait for X microseconds before sending next packet uX,
            defaults to "", uX for X microseconds, for example -i u1000
        :type pkt_interval: str
        :return: command output
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_hostname(self) -> str:
        """Get the hostname of the device.

        :return: hostname of the device
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def start_tcpdump(
        self,
        interface: str,
        port: str | None,
        output_file: str = "pkt_capture.pcap",
        filters: dict | None = None,
        additional_filters: str | None = "",
    ) -> str:
        """Start tcpdump capture on given interface.

        :param interface: inteface name where packets to be captured
        :type interface: str
        :param port: port number, can be a range of ports(eg: 443 or 433-443)
        :type port: str
        :param output_file: pcap file name, Defaults: pkt_capture.pcap
        :type output_file: str
        :param filters: filters as key value pair(eg: {"-v": "", "-c": "4"})
        :type filters: Optional[Dict]
        :param additional_filters: additional filters
        :type additional_filters: Optional[str]
        :raises ValueError: on failed to start tcpdump
        :return: console ouput and tcpdump process id
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def stop_tcpdump(self, process_id: str) -> None:
        """Stop tcpdump capture.

        :param process_id: tcpdump process id
        :type process_id: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_process_id(self, process_name: str) -> list[str] | None:
        """Return the process id to the device.

        :param process_name: name of the process
        :type process_name: str
        :return: process id if the process exist, else None
        :rtype: list[str] | None
        """
        raise NotImplementedError

    @abstractmethod
    def kill_process(self, pid: int, signal: int) -> None:
        """Kill the running process based on the process id.

        :param pid: process id
        :type pid: int
        :type signal: signal number to terminate the process
        :type signal: int
        """
        raise NotImplementedError
