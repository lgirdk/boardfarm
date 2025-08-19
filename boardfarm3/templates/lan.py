"""Boardfarm LAN device template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
    from ipaddress import IPv4Address

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.multicast import Multicast, MulticastGroupRecord
    from boardfarm3.lib.network_utils import NetworkUtility
    from boardfarm3.lib.networking import HTTPResult, IptablesFirewall, NSLookup

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
        """SOCKS5 Dante proxy address, e.g http://{proxy_ip}:{proxy_port}/."""
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

        :return: NSLookup utility instance with console object
        :rtype: NSLookup
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
    def start_ipv4_lan_client(
        self,
        wan_gw: str | IPv4Address | None = None,
        prep_iface: bool = False,
    ) -> str:
        """Restart IPv4 dhclient to obtain IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :type wan_gw: str | IPv4Address | None
        :param prep_iface: restart interface before dhclient request
        :type prep_iface: bool
        :return: IPv4 after renewal
        :rtype: str
        :raises pexpect.TimeoutException: in case of failure
        """
        raise NotImplementedError

    @abstractmethod
    def start_ipv6_lan_client(
        self,
        wan_gw: str | IPv4Address | None = None,
        prep_iface: bool = False,
    ) -> str:
        """Restart IPv6 dhclient to obtain IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :type wan_gw: str | IPv4Address | None
        :param prep_iface: restart interface before dhclient request
        :type prep_iface: bool
        :return: IPv6 after renewal
        :rtype: str
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
        :type interface: str
        :return: MAC address of the interface
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv4addr(self, interface: str) -> str:
        """Get IPv4 address of interface.

        :param interface: interface name
        :type interface: str
        :return: IPv4 address of the interface
        :rtype: str
        :raises BoardfarmException: in case IPv4 can not be found
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv6addr(self, interface: str) -> str:
        """Get IPv6 address of the interface.

        :param interface: interface name to get the link local
        :type interface: str
        :return: Global IPv6 address of the interface
        :rtype: str
        :raises BoardfarmException: in case IPv6 can not be found
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_link_local_ipv6addr(self, interface: str) -> str:
        """Get IPv6 link local address of the interface.

        :param interface: interface name
        :type interface: str
        :return: Link local ipv6 address of the interface
        :rtype: str
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

        :param ping_ip: ping IP
        :type ping_ip: str
        :param ping_count: number of ping, defaults to 4
        :type ping_count: int
        :param ping_interface: ping via interface, defaults to None
        :type ping_interface: str
        :param options: extra ping options, defaults to ""
        :type options: str
        :param timeout: timeout, defaults to 50
        :type timeout: int
        :param json_output: return ping output in dictionary format, defaults to False
        :type json_output: bool
        :return: ping output
        :rtype: bool | dict[str, Any]
        """
        raise NotImplementedError

    @abstractmethod
    def get_default_gateway(self) -> IPv4Address:
        """Get the default gateway from IP route output.

        :return: IPv4 of the default gateway
        :rtype: IPv4Address
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
    def renew_dhcp(self, interface: str) -> None:
        """Renew IPv4 of the specified interface by restart of the IPv4 dhclient.

        :param interface: interface name
        :type interface: str
        """
        raise NotImplementedError

    @abstractmethod
    def release_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Release IPv6 of the specified interface.

        :param interface: interface name
        :type interface: str
        :param stateless: run command with -S or -6 options. -6 by default
        :type stateless: bool
        """
        raise NotImplementedError

    @abstractmethod
    def renew_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Renew IPv6 of the specified interface.

        :param interface: interface name
        :type interface: str
        :param stateless: run command with -S or -6 options. -6 by default
        :type stateless: bool
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
        :type fname: str
        :param interface: name of the interface, defaults to "any"
        :type interface: str
        :param additional_args: argument arguments to tcpdump executable
        :type additional_args: str
        :return: tcpdump capture command console output
        :rtype: Generator[str, None, None]
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
        :type fname: str
        :param additional_args: additional arguments for tshark command
        :type additional_args: str
        :param timeout: time out for tshark command to be executed, defaults to 30
        :type timeout: int
        :param rm_pcap: If True remove the packet capture file after reading it
        :type rm_pcap: bool
        :return: return tshark read command console output
        :rtype: str
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

        :param host_ip: destination IP address
        :type host_ip: str | IPv4Address
        :param version: 4 or 6
        :type version: str
        :param options: traceroute command options
        :type options: str
        :param timeout: request timeout
        :type timeout: int
        :return: traceroute command output
        :rtype: str | None
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
        """Perform curl action to Web service.

        :param url : Web service address
        :type url : str
        :param protocol : Web Protocol (HTTP or HTTPS)
        :type protocol : str
        :param port : port number of server
        :type port : str | int | None
        :param options : Additional curl options
        :type options : str
        :return: True if curl action is successful
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def start_http_service(self, port: str, ip_version: str) -> str:
        """Start HTTP service on given port number.

        :param port: port number
        :type port: str
        :param ip_version: IP version, 4 - IPv4, 6 - IPv6
        :type ip_version: str
        :return: PID number of the HTTP service
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def stop_http_service(self, port: str) -> None:
        """Stop HTTP service running on given port.

        :param port: port number
        :type port: str
        """
        raise NotImplementedError

    @abstractmethod
    def http_get(self, url: str, timeout: int, options: str) -> HTTPResult:
        """Peform HTTP Get and return parsed result.

        :param url: URL to get the response
        :type url: str
        :param timeout: connection timeout for the curl command in seconds
        :type timeout: int
        :param options: additional curl options
        :type options: str
        :return: parsed HTTP response
        :rtype: HTTPResult
        """
        raise NotImplementedError

    @abstractmethod
    def dns_lookup(
        self, domain_name: str, record_type: str, opts: str = ""
    ) -> list[dict[str, Any]]:
        """Perform ``dig`` command in the devices to resolve DNS.

        :param domain_name: domain name which needs lookup
        :type domain_name: str
        :param record_type: AAAA for IPv6 else A
        :type record_type: str
        :param opts: options to be provided to dig command, defaults to ""
        :type opts: str
        :return: parsed dig command ouput
        :rtype: List[dict[str, Any]]
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
    def del_default_route(self, interface: str | None = None) -> None:
        """Remove the default gateway.

        :param interface: interface name, default to None
        :type interface: str | None
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

        :param ipaddr: IP address on which nmap is performed
        :type ipaddr: str
        :param ip_type: type of IP eg: IPv4/IPv6
        :type ip_type: str
        :param port: destination port on IP, defaults to None
        :type port: str | int | None
        :param protocol: specific protocol to follow eg: tcp(-sT)/udp(-sU),
            defaults to None
        :type protocol: str | None
        :param max_retries: number of port scan probe retransmissions, defaults to None
        :type max_retries: int | None
        :param min_rate: send packets no slower than per second, defaults to None
        :type min_rate: int | None
        :param opts: other options for a nmap command, defaults to None
        :type opts: str | None
        :param timeout: pexpect timeout for the command in seconds, defaults to 30
        :type timeout: int
        :raises BoardfarmException: if IP type is invalid
        :return: response of nmap command in XML/dict format
        :rtype: dict
        """
        raise NotImplementedError

    @abstractmethod
    def enable_ipv6(self) -> None:
        """Enable IPv6 on the connected client interface."""
        raise NotImplementedError

    @abstractmethod
    def disable_ipv6(self) -> None:
        """Disable IPv6 on the connected client interface."""
        raise NotImplementedError

    @abstractmethod
    def create_upnp_rule(
        self,
        int_port: str,
        ext_port: str,
        protocol: str,
        url: str,
    ) -> str:
        """Create UPnP rule on the device.

        :param int_port: internal port for UPnP
        :type int_port: str
        :param ext_port: external port for UPnP
        :type ext_port: str
        :param protocol: protocol to be used
        :type protocol: str
        :param url: url to be used
        :type url: str
        :return: output of upnpc add port command
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_upnp_rule(self, ext_port: str, protocol: str, url: str) -> str:
        """Delete UPnP rule on the device.

        :param ext_port: external port for UPnP
        :type ext_port: str
        :param protocol: protocol to be used
        :type protocol: str
        :param url: url to be used
        :type url: str
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
        :type bind_to_ip: str | None
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int | None
        :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2 as iperf3 does not support
            udp only flag for server
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
        :type bandwidth: int | None
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to None
        :type bind_to_ip: str | None
        :param direction: `--reverse` to run in reverse mode
            (server sends, client receives) or `--bidir` to run in
            bidirectional mode, defaults to None
        :type direction: str | None
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int | None
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
    def send_mldv2_report(
        self, mcast_group_record: MulticastGroupRecord, count: int
    ) -> None:
        """Send an MLDv2 report with desired multicast record.

        Multicast source and group must be IPv6 addresses.
        Multicast sources need to be non-multicast addresses and
        group address needs to be a multicast address.

        Implementation relies on a custom send_mld_report
        script based on scapy.

        :param mcast_group_record: MLDv2 multicast group record
        :type mcast_group_record: MulticastGroupRecord
        :param count: num of packets to send in 1s interval
        :type count: int
        :raises CodeError: if send_mld_report command fails
        """
        raise NotImplementedError

    @abstractmethod
    def netcat(self, host_ip: str, port: str, additional_args: str) -> None:
        """Run netcat command to initiate brute force.

        :param host_ip: host ip address
        :type host_ip: str
        :param port: port number of the host
        :type port: str
        :param additional_args: additional args to be provided with netcat command
        :type additional_args: str
        """
        raise NotImplementedError

    @abstractmethod
    def start_nping(  # pylint: disable=too-many-arguments # noqa: PLR0913
        self,
        interface_ip: str,
        ipv6_flag: bool,
        extra_args: str,
        port_range: str,
        hit_count: str,
        rate: str,
        mode: str,
    ) -> str:
        """Perform nping.

        :param interface_ip: interface ip addr
        :type interface_ip: str
        :param ipv6_flag: flag if ipv6 addr to be used
        :type ipv6_flag: bool
        :param extra_args: any extra arguments
        :type extra_args: str
        :param port_range: target port range
        :type port_range: str
        :param hit_count: the number of times to target each host
        :type hit_count: str
        :param rate: num of packets per second to send
        :type rate: str
        :param mode: probe mode. tcp/udp/icmp etc protocol
        :type mode: str
        :return: process id
        :rtype: str
        :raises ValueError: if unable to start nping.
        """
        raise NotImplementedError

    @abstractmethod
    def stop_nping(self, process_id: str) -> None:
        """Stop nping process running in background.

        :param process_id: process id of nping
        :type process_id: str
        :raises BoardfarmException: when unable to stop process
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
    def add_hosts_entry(self, ip: str, host_name: str) -> None:
        """Add entry in hosts file.

        :param ip: host ip addr
        :type ip: str
        :param host_name: host name to be added
        :type host_name: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_hosts_entry(self, host_name: str, ip: str) -> None:
        """Delete entry in hosts file.

        :param host_name: host name to be deleted
        :type host_name: str
        :param ip: host ip addr
        :type ip: str
        """
        raise NotImplementedError

    @abstractmethod
    def flush_arp_cache(self) -> None:
        """Flushes arp cache entries."""
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
    def get_arp_table(self) -> str:
        """Fetch ARP table output.

        :return: output of arp command
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_arp_table_entry(self, ip: str, intf: str) -> None:
        """Delete ARP table output.

        :param ip: ip of the host entry to be deleted
        :type ip: str
        :param intf: interface for which the entry needs to be deleted
        :type intf: str
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
