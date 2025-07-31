"""Common Networking use cases."""
# pylint: disable=too-many-lines

from __future__ import annotations

import ipaddress
import logging
import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeAlias

from termcolor import colored

from boardfarm3.exceptions import UseCaseFailure
from boardfarm3.lib.networking import nmap
from boardfarm3.lib.shell_prompt import DEFAULT_BASH_SHELL_PROMPT_PATTERN
from boardfarm3.lib.utils import ip_pool_to_list
from boardfarm3.templates.acs import ACS
from boardfarm3.templates.cpe import CPE
from boardfarm3.templates.lan import LAN
from boardfarm3.templates.wan import WAN
from boardfarm3.templates.wlan import WLAN

if TYPE_CHECKING:
    from collections.abc import Generator

    from pandas import DataFrame

    from boardfarm3.lib.dataclass.packets import ICMPPacketData
    from boardfarm3.lib.network_utils import NetworkUtility
    from boardfarm3.lib.networking import HTTPResult


_LOGGER = logging.getLogger(__name__)

DeviceWithFwType: TypeAlias = LAN | WAN | ACS | CPE
SSHDeviceType: TypeAlias = LAN | WAN | WLAN


def __get_dev_s_network_utility(
    device: LAN | WAN | CPE,
) -> NetworkUtility:
    return device.sw.nw_utility if isinstance(device, CPE) else device.nw_utility


def ping(  # noqa: PLR0913
    device: LAN | WAN | WLAN,
    ping_ip: str,
    ping_count: int = 4,
    ping_interface: str | None = None,
    timeout: int = 50,
    json_output: bool = False,
    options: str = "",
) -> bool | dict[str, Any]:
    """Ping remote host IP.

    Return True if ping has 0% loss or parsed output in JSON if
    json_output=True flag is provided.

    :param device: device on which ping is performed
    :type device: LAN | WAN
    :param ping_ip: IP to ping
    :type ping_ip: str
    :param ping_count: number of concurrent pings, defaults to 4
    :type ping_count: int
    :param ping_interface: ping via interface, defaults to None
    :type ping_interface: str | None
    :param timeout: timeout, defaults to 50
    :type timeout: int
    :param json_output: True if ping output in dictionary format else False,
        defaults to False
    :type json_output: bool
    :param options: extra ping options, defaults to ""
    :type options: str
    :return: bool or dict of ping output
    :rtype: bool | dict[str, Any]
    """
    return device.ping(
        ping_ip,
        ping_count,
        ping_interface,
        timeout=timeout,
        json_output=json_output,
        options=options,
    )


@contextmanager
def start_http_server(
    device: LAN | WAN,
    port: int | str,
    ip_version: str | int,
) -> Generator:
    """Start http server on given client.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start the HTTP server on the [] client

    :param device: device on which server will start
    :type device: LAN | WAN
    :param port: port on which the server listen for incomming connections
    :type port: int | str
    :param ip_version: ip version of server values can strictly be 4 or 6
    :type ip_version: str | int
    :raises ValueError: wrong ip_version value is given in api call
    :yield: PID of the http server process
    """
    port = str(port)
    ip_version = str(ip_version)
    if ip_version not in ["4", "6"]:
        reason = f"Invalid ip_version argument {ip_version}."
        raise ValueError(reason)
    # stop http service if running
    device.stop_http_service(port)
    try:
        yield device.start_http_service(port, ip_version)
    finally:
        device.stop_http_service(port)


def http_get(  # noqa: PLR0913
    device: LAN | WAN,
    url: str,
    timeout: int = 20,
    no_proxy: bool = False,
    is_insecure: bool = False,
    follow_redirects: bool = False,
) -> HTTPResult:
    """Check if the given HTTP server is running.

    This Use Case executes a curl command with a given timeout from the given
    client. The destination is specified by the URL parameter

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify HTTP server is accessible from [] via eRouter IP
        - Verify that the HTTP server running on the client is accessible
        - Try to connect to the HTTP server from [] client

    :param device: the device from where HTTP response to get
    :type device: LAN | WAN
    :param url: URL to get the response
    :type url: str
    :param timeout: connection timeout for the curl command in seconds, default 20
    :type timeout: int
    :param no_proxy: no_proxy option for curl command, defaults to False
    :type no_proxy: bool
    :param is_insecure: is_insecure option for curl command, defaults to False
    :type is_insecure: bool
    :param follow_redirects: follow_redirects option for curl command, defaults to False
    :type follow_redirects: bool
    :return: parsed HTTP Get response
    :rtype: HTTPResult
    """
    options = ""
    if no_proxy:
        options += "--noproxy '*' "
    if is_insecure:
        options += "-k "
    if follow_redirects:
        options += "-L "
    return device.http_get(url, timeout, options)


def is_icmp_packet_present(
    captured_sequence: list[ICMPPacketData],
    expected_sequence: list[ICMPPacketData],
) -> bool:
    """Check whether the expected ICMP sequence matches with the captured sequence.

    :param captured_sequence: Sequence of ICMP packets filtered from captured pcap file
    :type captured_sequence: List[ICMPPacketData]
    :param expected_sequence: Example for IPv4 source and destination and ``query_code``
        as 8 (Echo Request)

            .. code-block:: python

                [
                    ICMPPacketData(
                        IPAddresses(IPv4Address("172.25.1.109"), None, None),
                        IPAddresses(IPv4Address("192.168.178.22"), None, None),
                        8,
                    ),
                ]

    .. hint:: This Use Case implements statements from the test suite such as:

        - Check whether the expected ICMP sequence matches with the captured sequence.

    :type expected_sequence: List[ICMPPacketData]
    :return: True if ICMP expected sequences matches with the captured sequence
    :rtype: bool
    """
    last_check = 0
    final_result = []
    for icmp_packet_expected in expected_sequence:
        for i in range(last_check, len(captured_sequence)):
            if captured_sequence[i] == icmp_packet_expected:
                last_check = i
                _LOGGER.info(
                    colored(
                        f"Verified ICMP packet:\t{icmp_packet_expected.source}\t"
                        f"-->>\t{icmp_packet_expected.destination}\tType:"
                        f" {icmp_packet_expected.query_code}",
                        color="green",
                    ),
                )
                final_result.append(True)
                break
        else:
            _LOGGER.info(
                colored(
                    "Couldn't verify ICMP packet:\t"
                    f"{icmp_packet_expected.source}\t-->>\t"
                    f"{icmp_packet_expected.destination}\tType:"
                    f" {icmp_packet_expected.query_code}",
                    color="red",
                ),
            )
            final_result.append(False)
    return all(final_result)


def is_client_ip_in_pool(
    pool_bounds: tuple[ipaddress.IPv4Address, ipaddress.IPv4Address],
    client: LAN | WAN,
) -> bool:
    """Check for client IP in IP pool.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Configure the LAN client with Static IP from the higher range of the subnet
          defined in the config file and Default gateway is set to the lowest IP
          (eRouter LAN interface) address of subnet

    :param pool_bounds: lowest and highest IP from DHCP pool
    :type pool_bounds: tuple[ipaddress.IPv4Address, ipaddress.IPv4Address]
    :param client: client to be checked
    :type client: LAN | WAN
    :return: True if LAN/WIFILAN IP is lowest in pool range
    :rtype: bool
    """
    lan_ip_address = ipaddress.IPv4Address(
        client.get_interface_ipv4addr(client.iface_dut),
    )
    ip_range = ip_pool_to_list(*pool_bounds)
    return lan_ip_address in ip_range


def dns_lookup(
    host: LAN | WAN, domain_name: str, ipv6: bool = False, opts: str = ""
) -> list[dict[str, Any]]:
    """Perform ``dig`` command in the devices to resolve DNS.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify that IPv4 domain name can be resolved to IP.
        - Verify the DNS IPv4 address assigned by the service provider

    :param host: host where the dig command has to be run
    :type host: LAN | WAN
    :param domain_name: domain name which needs lookup
    :type domain_name: str
    :param ipv6: flag to perform IPv4 or IPv6 lookup, defaults to False
    :type ipv6: bool
    :param opts: options to be provided to dig command, defaults to ""
    :type opts: str
    :return: returns dig output from jc parser
    :rtype: List[Dict[str, Any]]
    :raises UseCaseFailure: when domain_name cannot resolve
    """
    record_type = "AAAA" if ipv6 else "A"
    result = host.dns_lookup(domain_name, record_type, opts)
    if result:
        return result
    msg = f"Failed to resolve {domain_name}"
    raise UseCaseFailure(msg)


def create_udp_session(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_device: LAN | WLAN | WAN,
    destination_device: LAN | WLAN | WAN | CPE,
    ip_type: str,
    port: str | int,
    max_retries: int,
    timeout: int = 30,
) -> dict[str, str]:
    """Create a UDP session from source to destination device on a port.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Create a UDP session from source to destination device on a port.

    Runs nmap network utility on source device.

    :param source_device: Source device
    :type source_device: LAN | WLAN | WAN
    :param destination_device: Destination device
    :type destination_device: LAN | WLAN | WAN | CPE
    :param ip_type: type of ipaddress: "ipv4", "ipv6"
    :type ip_type: str
    :param port: port or range of ports: "666-999"
    :type port: str | int
    :param max_retries: maximum number retries for nmap
    :type max_retries: int
    :param timeout: pexpect timeout for the command in seconds, defaults to 30
    :type timeout: int
    :return: XML output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return nmap(
        source_device,
        destination_device,
        ip_type,
        port,
        "-sU",
        max_retries,
        timeout=timeout,
    )


def create_tcp_session(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_device: LAN | WLAN | WAN,
    destination_device: LAN | WLAN | WAN | CPE,
    ip_type: str,
    port: str | int,
    max_retries: int = 4,
    timeout: int = 30,
) -> dict[str, str]:
    """Create a TCP session from source to destination device on a port.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Create a TCP session from source to destination device on a port.

    Runs nmap network utility on source device.

    :param source_device: Source device
    :type source_device: LAN | WLAN | WAN
    :param destination_device: destination device
    :type destination_device: LAN | WLAN | WAN | CPE
    :param ip_type: type of IP address: "ipv4", "ipv6"
    :type ip_type: str
    :param port: port or range of ports: "666-999"
    :type port: str | int
    :param max_retries: maximum number retries for nmap
    :type max_retries: int
    :param timeout: pexpect timeout for the command in seconds, defaults to 30
    :type timeout: int
    :return: XML output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return nmap(
        source_device,
        destination_device,
        ip_type,
        port,
        "-sT",
        max_retries,
        timeout=timeout,
    )


def create_tcp_udp_session(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_device: LAN | WLAN | WAN,
    destination_device: LAN | WLAN | WAN | CPE,
    ip_type: str,
    port: str | int,
    max_retries: int = 4,
    timeout: int = 30,
) -> dict[str, str]:
    """Create both TCP and UDP session from source to destination device on a port.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Run nmap from client to erouter WAN IP.

    Runs nmap network utility on source device.

    :param source_device: source device
    :type source_device: LAN | WLAN | WA
    :param destination_device: destination device
    :type destination_device: LAN | WLAN | WAN | CPE
    :param ip_type: type of IP address: "ipv4", "ipv6"
    :type ip_type: str
    :param port: port or range of ports: "666-999"
    :type port: str | int
    :param max_retries: maximum number retries for nmap
    :type max_retries: int
    :param timeout: pexpect timeout for the command in seconds, defaults to 30
    :type timeout: int
    :return: XML output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return nmap(
        source_device,
        destination_device,
        ip_type,
        port,
        "-sU -sT",
        max_retries,
        timeout=timeout,
    )


def trigger_ip_flood(  # noqa: PLR0913
    source_device: LAN | WLAN | WAN,
    destination_device: LAN | WLAN | WAN | CPE,
    ip_type: str,
    port: str | int,
    min_rate: int,
    max_retries: int = 4,
    timeout: int = 30,
) -> dict[str, str]:
    """Perform IP flooding via nmap network utility on source device.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Perform IP flooding via nmap network utility on source device.

    :param source_device: source device
    :type source_device: LAN | WLAN | WAN
    :param destination_device: destination device
    :type destination_device: LAN | WLAN | WAN | CPE
    :param ip_type: type of IP address: "ipv4", "ipv6"
    :type ip_type: str
    :param port: port or range of ports: "666-999"
    :type port: str | int
    :param min_rate: send packets no slower than min_rate per second
    :type min_rate: int
    :param max_retries: maximum number retries for nmap
    :type max_retries: int
    :param timeout: pexpect timeout for the command in seconds, defaults to 30
    :type timeout: int
    :return: XML output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return nmap(
        source_device,
        destination_device,
        ip_type,
        port,
        "-sS",
        max_retries,
        min_rate,
        timeout=timeout,
    )


def nmap_scan(
    source_device: LAN | WLAN | WAN,
    destination_device: LAN | WLAN | WAN | CPE,
    ip_type: str,
    timeout: int = 30,
) -> dict[str, str]:
    """Perform Complete scan on destination via nmap network utility on source device.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Perform Complete scan on destination via nmap network utility on source device

    :param source_device: source device
    :type source_device: LAN | WLAN | WAN
    :param destination_device: destination device
    :type destination_device: LAN | WLAN | WAN | CPE
    :param ip_type: type of IP address: "ipv4", "ipv6"
    :type ip_type: str
    :param timeout: pexpect timeout for the command in seconds, defaults to 30
    :type timeout: int
    :return: XML output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return nmap(source_device, destination_device, ip_type, opts="-F", timeout=timeout)


def enable_ipv6(device: LAN | WLAN) -> None:
    """Enable IPv6 on the specified interface.

    The Use Case executes the following commands:
        - sysctl net.ipv6.conf.<interface>.disable_ipv6=0
        - sysctl net.ipv6.conf.<interface>.accept_ra=2

    .. hint:: This Use Case implements statements from the test suite such as:

        - Enable IPv6 on the specified interface.

    :param device: LAN or WLAN device object
    :type device: LAN | WLAN
    """
    device.enable_ipv6()


def disable_ipv6(device: LAN | WLAN) -> None:
    """Disable ipv6 on the specified interface.

    The use case executes the following commands:
        - sysctl net.ipv6.conf.<interface>.disable_ipv6=1

    .. hint:: This Use Case implements statements from the test suite such as:

        - Disable IPv6 on the specified interface.

    :param device: LAN or WLAN device object
    :type device: LAN | WLAN
    """
    device.disable_ipv6()


def get_interface_mac_addr(device: LAN | WLAN | WAN | CPE, interface: str) -> str:
    """Get the MAC address of the provided interface.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Get the mac address of the provided interface.

    :param device: device having the interface
    :type device: LAN | WLAN | WAN | CPE
    :param interface: interface name
    :type interface: str
    :return: MAC address of the provided interface
    :rtype: str
    """
    return (
        device.sw.get_interface_mac_addr(interface)
        if isinstance(device, CPE)
        else device.get_interface_macaddr(interface)
    )


def get_iptables_list(
    device: DeviceWithFwType,
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> dict[str, list[dict]]:
    """Return iptables rules as dictionary.

    :param device: type of the device
    :type device: DeviceWithFwType
    :param opts: _command line arguments for iptables command, defaults to ""
    :type opts: str
    :param extra_opts: extra command line arguments for iptables command,
        defaults to -nvL --line-number
    :type extra_opts: str
    :return: iptables rules dictionary
    :rtype: dict[str, list[dict]]
    """
    return (
        device.firewall.get_iptables_list(opts, extra_opts)
        if not isinstance(device, CPE)
        else device.sw.firewall.get_iptables_list(opts, extra_opts)
    )


def get_ip6tables_list(
    device: DeviceWithFwType,
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> dict[str, list[dict]]:
    """Return ip6tables rules as dictionary.

    :param device: type of the device
    :type device: DeviceWithFwType
    :param opts: _command line arguments for ip6tables command, defaults to ""
    :type opts: str
    :param extra_opts: extra command line arguments for ip6tables command,
        defaults to -nvL --line-number
    :type extra_opts: str
    :return: ip6tables rules dictionary
    :rtype: dict[str, list[dict]]
    """
    return (
        device.firewall.get_ip6tables_list(opts, extra_opts)
        if not isinstance(device, CPE)
        else device.sw.firewall.get_ip6tables_list(opts, extra_opts)
    )


def is_iptable_empty(
    device: DeviceWithFwType,
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> bool:
    """Return True if iptables is empty.

    :param device: type of the device
    :type device: DeviceWithFwType
    :param opts: command line arguments for iptables command, defaults to ""
    :type opts: str
    :param extra_opts: extra command line arguments for iptables command, defaults to ""
    :type extra_opts: str
    :return: True if iptables is empty, False otherwise
    :rtype: bool
    """
    return (
        device.firewall.is_iptable_empty(opts, extra_opts)
        if not isinstance(device, CPE)
        else device.sw.firewall.is_iptable_empty(opts, extra_opts)
    )


def is_ip6table_empty(
    device: DeviceWithFwType,
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> bool:
    """Return True if ip6tables is empty.

    :param device: type of the device
    :type device: DeviceWithFwType
    :param opts: command line arguments for ip6tables command, defaults to ""
    :type opts: str
    :param extra_opts: extra command line arguments for ip6tables command,
        defaults to ""
    :type extra_opts: str
    :return: True if ip6tables is empty, False otherwise
    :rtype: bool
    """
    return (
        device.firewall.is_ip6table_empty(opts, extra_opts)
        if not isinstance(device, CPE)
        else device.sw.firewall.is_ip6table_empty(opts, extra_opts)
    )


def get_iptables_policy(
    device: DeviceWithFwType,
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> dict[str, str]:
    """Return iptables policies as dictionary.

    :param device: type of the device
    :type device: DeviceWithFwType
    :param opts: command line arguments for iptables command, defaults to ""
    :type opts: str
    :param extra_opts: extra command line arguments for iptables command,
        defaults to "-nvL --line-number"
    :type extra_opts: str
    :return: iptables policies dictionary
    :rtype: dict[str, str]
    """
    return (
        device.firewall.get_iptables_policy(opts, extra_opts)
        if not isinstance(device, CPE)
        else device.sw.firewall.get_iptables_policy(opts, extra_opts)
    )


def get_nslookup_data(
    device: LAN | WAN,
    domain_name: str,
    opts: str = "",
    extra_opts: str = "",
) -> dict[str, Any]:
    """Perform nslookup with given arguments and return the parsed results.

    to get A records, pass -q=A in opts

    to get AAAA records, pass -q=AAAA in opts

    to just get the DNS records, opts and extra opts are not needed

    :param device: type of the device
    :type device: Union[LAN, WAN]
    :param domain_name: domain name to perform nslookup on
    :type domain_name: str
    :param opts: nslookup command line options, defaults to ""
    :type opts: str
    :param extra_opts: nslookup additional command line options, defaults to ""
    :type extra_opts: str
    :return: parsed nslookup results as dictionary
    :rtype: dict[str, Any]
    """
    return device.nslookup.nslookup(domain_name, opts, extra_opts)


def get_ip6tables_policy(
    device: DeviceWithFwType,
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> dict[str, str]:
    """Get firewall's ip6tables policy.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Get the Firewall's ip6tables policy

    :param device: device instance
    :type device: DeviceWithFwType
    :param opts: options for ip6tables command, defaults to ""
    :type opts: str
    :param extra_opts: options for ip6tables command, defaults to "-nvL --line-number"
    :type extra_opts: str
    :return: dict of ip6tables policy
    :rtype: dict[str, str]
    """
    return (
        device.firewall.get_ip6tables_policy(opts, extra_opts)
        if not isinstance(device, CPE)
        else device.sw.firewall.get_ip6tables_policy(opts, extra_opts)
    )


def netcat(device: LAN, host_ip: str, port: str, additional_args: str) -> None:
    """Run netcat command to initiate brute force.

    :param device: lan device
    :type device: LAN
    :param host_ip: host ip address
    :type host_ip: str
    :param port: port number of the host
    :type port: str
    :param additional_args: additional args to be provided in netcat command
    :type additional_args: str
    """
    device.netcat(host_ip, port, additional_args)


@contextmanager
def nping(  # pylint: disable=too-many-arguments # noqa: PLR0913
    device: LAN,
    interface_ip: str,
    ipv6: bool = False,
    extra_args: str = "",
    port_range: str = "0-65535",
    hit_count: str = "2",
    rate: str = "200",
    mode: str = "udp",
) -> Generator[str]:
    """Perform nping command and kill process once done.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Execute the command from the connected LAN Client to do nping
          on [] side network

    :param device: connected client to perform nping command from.
    :type device: LAN
    :param interface_ip: interface ip addr
    :type interface_ip: str
    :param ipv6: if ipv6 addr to be used, defaults to False
    :type ipv6: bool
    :param extra_args: any extra arguments
    :type extra_args: str
    :param port_range: target port range, defaults to all ports
    :type port_range: str
    :param hit_count: the number of times to target each host,
        defaults to 2
    :type hit_count: str
    :param rate: num of packets per second to send, defaults to 200
    :type rate: str
    :param mode: probe mode. tcp/udp/icmp etc protocol, defaults to udp
    :type mode: str
    :yield: process id
    :rtype: Generator[str, None, None]
    """
    pid: str = ""
    try:
        pid = device.start_nping(
            interface_ip, ipv6, extra_args, port_range, hit_count, rate, mode
        )
        yield pid
    finally:
        device.stop_nping(process_id=pid)


def netstat_listening_ports(
    device: CPE | LAN | WAN,
    opts: str = "-nlp",
    extra_opts: str = "",
) -> DataFrame:
    """Get all listening ports.

    :param device: type of the device
    :type device: CPE | LAN | WAN
    :param opts: command line options
    :type opts: str
    :param extra_opts: extra command line options
    :type extra_opts: str
    :return: parsed netstat output
    :rtype: DataFrame
    """
    device_nw = __get_dev_s_network_utility(device)
    return device_nw.netstat(opts, extra_opts)


def netstat_all_udp(
    device: CPE | LAN | WAN,
    opts: str = "-au",
    extra_opts: str = "",
) -> DataFrame:
    """Get all UDP ports.

    :param device: type of the device
    :type device: CPE | LAN | WAN
    :param opts: command line options
    :type opts: str
    :param extra_opts: extra command line options
    :type extra_opts: str
    :return: parsed netstat output
    :rtype: DataFrame
    """
    device_nw = __get_dev_s_network_utility(device)
    return device_nw.netstat(opts, extra_opts)


def netstat_all_tcp(
    device: CPE | LAN | WAN,
    opts: str = "-at",
    extra_opts: str = "",
) -> DataFrame:
    """Get all TCP ports.

    :param device: type of the device
    :type device: CPE | LAN | WAN
    :param opts: command line options
    :type opts: str
    :param extra_opts: extra command line options
    :type extra_opts: str
    :return: parsed netstat output
    :rtype: DataFrame
    """
    device_nw = __get_dev_s_network_utility(device)
    return device_nw.netstat(opts, extra_opts)


def connect_via_ssh(
    from_which_device: SSHDeviceType,
    to_which_device: SSHDeviceType,
    protocol: int = 4,
    username: str = "root",
    password: str = "bigfoot1",  # noqa: S107
) -> bool:
    """SSH from a device to another.

    This use case validates if SSH is possible from a device to another.

    :param from_which_device: Device initiating the SSH connection
    :type from_which_device: SSHDeviceType
    :param to_which_device: Target SSH device
    :type to_which_device: SSHDeviceType
    :param protocol: IP address family, defaults to 4
    :type protocol: int
    :param username: SSH username, defaults to root
    :type username: str
    :param password: SSH password, defaults to bigfoot1
    :type password: str
    :raises ConnectionError: If connectivity exists, but SSH not successful
    :return: True if SSH successful, else False
    :rtype: bool
    """
    def_protocol = 4
    address = (
        to_which_device.ipv4_addr
        if protocol == def_protocol
        else to_which_device.ipv6_addr
    )
    ssh_command = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
        -o UserKnownHostsFile=/dev/null {username}@{address} exit"
    from_which_device.console.sendline(ssh_command)
    index = from_which_device.console.expect(
        ["assword:", DEFAULT_BASH_SHELL_PROMPT_PATTERN]
    )
    if index == 0:
        from_which_device.console.sendline(f"{password}")
        index = from_which_device.console.expect(
            ["assword:", DEFAULT_BASH_SHELL_PROMPT_PATTERN]
        )
        if index == 0:
            from_which_device.console.sendcontrol("c")
            from_which_device.console.expect(DEFAULT_BASH_SHELL_PROMPT_PATTERN)
            return False
        if from_which_device.console.execute_command("echo $?") != "0":
            msg = "SSH not successful - needs troubleshooting."
            raise ConnectionError(msg)
        return True
    return False


def hping_flood(  # noqa: PLR0913
    device: LAN | WAN,
    protocol: str,
    target: str,
    packet_count: str,
    extra_args: str | None = None,
    pkt_interval: str = "",
) -> str:
    """Validate SYN, UDP and ICMP flood operation.

    .. hint:: This Use Case implements statements from the test suite such as:

        - To validate SYN flood, ICMP flood (from WAN & LAN) and UDP flood (from WAN)

    :param device: object of the device class where tcpdump is captured
    :type device: LAN | WAN
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
    return device.hping_flood(
        protocol=protocol,
        target=target,
        packet_count=packet_count,
        extra_args=extra_args,
        pkt_interval=pkt_interval,
    )


def verify_tunnel_packets(
    captured_sequence: list[tuple[str, ...]],
    expected_sequence: list[tuple[str, ...]],
) -> bool:
    """Verify the expected encapsulated info with the captured sequence.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Traffic from Ethernet LAN client to Internet, must be encapsulated like below

    :param captured_sequence: Sequence of packets filtered from captured pcap file
    :type captured_sequence: list[tuple[str, ...]]
    :param expected_sequence: Example for encapsulated traffic

            .. code-block:: python

                [
                    (
                        "10.1.2.105,10.15.137.242",
                        "44:d4:54:e1:9e:57,44:d4:54:e1:9e:57",
                        "172.30.113.175,8.8.8.8",
                        "52:54:00:67:85:42,52:54:00:67:85:42",
                    )
                ]

    :type expected_sequence: list[tuple[str, ...]]
    :return: True if ICMP expected sequences matches with the captured sequence
        and encapsulated as expected sequence with outer and inner layer
    :rtype: bool
    """
    final_result = []
    last_check = 0
    for packet in expected_sequence:
        for i in range(last_check, len(captured_sequence)):
            if all(
                expected == actual
                for expected, actual in zip(packet, captured_sequence[i])
                if expected != "*"
            ):
                last_check = i
                _LOGGER.debug(
                    "Verified encapsulated packets: %s,%s,%s,%s",
                    packet[0],
                    packet[1],
                    packet[2],
                    packet[3],
                )
                final_result.append(captured_sequence[i])
                break
        else:
            _LOGGER.debug(
                "Failed verification: %s,%s,%s,%s",
                packet[0],
                packet[1],
                packet[2],
                packet[3],
            )
            final_result.append(())
    return all(final_result)


def flush_arp_cache(device: LAN) -> None:
    """Flushes arp cache entries.

    .. hint:: This Use Case implements statements from the test suite such as:

        Generate ARP Request for...

    - ping can be used post clearing cache and ARP pakcets can be ovserved in
        pkt capture

    :param device: device on which cache to be cleared
    :type device: LAN
    """
    device.flush_arp_cache()


def get_arp_table_info(device: LAN) -> list[dict[str, str]]:
    """Fetch arp entries.

    .. hint:: This Use Case implements statements from the test suite such as:

        Show ARP table / Get ARP entries

    :param device: device on which cache to be cleared
    :type device: LAN
    :return: list of parsed ARP table entries
    :rtype: list[dict[str, str]]
    """
    arp_table: list[dict[str, str]] = []
    out = device.get_arp_table()
    arp_regex = re.compile(
        r"(?P<address>\d+.\d+.\d+.\d+)\s+(?P<hw_type>\S+)\s+"
        r"(?P<hw_address>\S+)\s+(?P<flags_mask>\S+)\s+(?P<iface>\S+)"
    )
    for entry in out.splitlines()[1:]:
        arp_entry = re.search(arp_regex, entry)
        if arp_entry:
            arp_table.append(arp_entry.groupdict())
    return arp_table


def delete_arp_table_entry(device: LAN, ip: str, intf: str) -> None:
    """Delete arp table entry.

    .. hint:: This Use Case implements statements from the test suite such as:

        Delete ARP table entry

    :param device: device on which cache to be cleared
    :type device: LAN
    :param ip: ip of the host entry to be deleted
    :type ip: str
    :param intf: interface on which the host needs to be deleted
    :type intf: str
    """
    device.delete_arp_table_entry(ip, intf)
