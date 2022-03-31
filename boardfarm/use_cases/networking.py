"""All APIs are independent of board under test.
"""
import ipaddress
import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import jc.parsers.dig
import pexpect
from bs4 import BeautifulSoup
from termcolor import colored

from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.devices.debian_wan import DebianWAN
from boardfarm.devices.debian_wifi import DebianWifi
from boardfarm.exceptions import BftIfaceNoIpV6Addr, PexpectErrorTimeout, UseCaseFailure
from boardfarm.lib.common import http_service_kill, ip_pool_to_list
from boardfarm.lib.DeviceManager import get_device_by_name

from .voice import VoiceClient

logger = logging.getLogger("bft")


@dataclass
class IPAddresses:
    """This is an IP address data classes to hold ip objects or None."""

    ipv4: Optional[IPv4Address]
    ipv6: Optional[IPv6Address]
    link_local_ipv6: Optional[IPv6Address]


@dataclass
class ICMPPacketData:
    """ICMP packet data class to hold all the packet information specific to ICMP packets
    source and destination could be either ipv4 or ipv6 addresses
    query_code defines the type of message received or sent and could be among the following:
        Type 0 = Echo Reply
        Type 8 = Echo Request
        Type 9 = Router Advertisement
        Type 10 = Router Solicitation
        Type 13 = Timestamp Request
        Type 14 = Timestamp Reply
    """

    source: IPAddresses
    destination: IPAddresses
    query_code: int


class HTTPResult:
    def __init__(self, response: str):
        self.response = response

        # Todo: Wget parsing has to be added

        def parse_response(response: str = response):
            if "Connection refused" in response:
                raise UseCaseFailure(
                    f"Curl Failure due to the following reason {response}"
                )
            else:
                raw = re.findall(r"\<\!.*\>", response, re.S)[0]
                code = re.findall(r"< HTTP\/.*\s(\d+)", response)[0]
                beautified_text = print(BeautifulSoup(raw, "html.parser").prettify())
                return raw, code, beautified_text

        self.raw, self.code, self.beautified_text = parse_response(response)


@contextmanager
def start_wan_ipv6_http_server(port: int = 9001) -> str:
    """To start wan http server.
    :param mode: mode to run the server ipv6/ipv4
    :type mode: string
    :param port: port in which the http server should run
    :type port: int
    :param options: options to start the server
    :type options: string
    :return: url
    :rtype: string
    """
    wan = get_device_by_name("wan")
    http_service_kill(wan, "SimpleHTTPServer")
    try:
        ip = wan.get_interface_ip6addr(wan.iface_dut)
        wan.sendline(
            f"""cat > /root/SimpleHTTPServer6.py<<EOF
import socket
import BaseHTTPServer as bhs
import SimpleHTTPServer as shs
class HTTPServerV6(bhs.HTTPServer):
    address_family = socket.AF_INET6
HTTPServerV6(("{ip}", {str(port)}),shs.SimpleHTTPRequestHandler).serve_forever()
EOF"""
        )
        wan.expect(wan.prompt)
        wan.sendline("python -m /root/SimpleHTTPServer6 &")
        if 0 == wan.expect(["Traceback", pexpect.TIMEOUT], timeout=10):
            raise UseCaseFailure("Http server is not started")
        yield f"[{ip}]:{str(port)}"
    finally:
        http_service_kill(wan, "SimpleHTTPServer")


def is_wan_http_server_running() -> bool:
    """To check if wan http server is running.
    :return: True/False
    :rtype: bool
    """
    wan = get_device_by_name("wan")
    # to be done with netstat later
    wan.sendline("ps -elf | grep HTTP")
    index = wan.expect(["SimpleHTTPServer"] + wan.prompt)
    if index == 0:
        return True
    return False


def http_get(which_client: Union[DebianWifi, VoiceClient], url: str) -> str:
    """To check if wan http server is running.
    :param which_client : the client from where http response is got
    :type which_client: Union[DebianWifi, VoiceClient]
    :param url : url to get the response
    :type url: string
    :return: Http response
    :rtype: object
    """
    client = which_client._obj() if type(which_client) == VoiceClient else which_client

    client.sendline(f"curl -v {url}")
    client.expect(client.prompt)
    return HTTPResult(client.before)


@contextmanager
def tcpdump_on_board(
    fname: str, interface: str, filters: str = ""
) -> Generator[str, None, None]:
    """Contextmanager to start the tcpdump on the board console and kills the
    process outside its scope

    Args:
        fname (str): the filename or the complete path of the resourcel
        interface (str): interface name on which the tcp traffic will listen to
        filters (str, optional): Additional filters for the tcpdump command. Defaults to "".

    Yields:
        Generator[str, None, None]: Yields the process id of the tcp capture started
    """
    pid: str = ""
    board = get_device_by_name("board")
    try:
        pid = board.nw_utility.start_tcpdump(fname, interface, filters=filters)
        yield pid
    finally:
        board.nw_utility.stop_tcpdump(pid)


def read_tcpdump_from_board(
    fname: str, protocol: str = "", opts: str = "", rm_pcap=True
) -> str:
    """Read the tcpdump packets and deletes the capture file after read

    Args:
        fname (str): filename or the complete path of the pcap file
        protocol (str, optional): protocol to filter. Defaults to ""
        opts (str, optional): [description]. Defaults to "".
        rm_pcap (bool, optional): [description]. Defaults to True.

    Returns:
        str: Output of tcpdump read command
    """
    board = get_device_by_name("board")
    return board.nw_utility.read_tcpdump(
        fname, protocol=protocol, opts=opts, rm_pcap=rm_pcap
    )


def perform_scp_action_on_board(
    path_on_board: str, path_on_host: str, which_host: str, action: str
) -> None:
    """Allows you to securely copy files and directories between the board and the remote host

    Args:
        path_on_board (str): Path on the board
        path_on_host (str): Path on the remote host
        which_host (str): name of the remote host i.e lan, lan2, wan
        action (str): scp action to perform i.e upload, download
    """
    (src, dst) = (
        (path_on_board, path_on_host)
        if action == "upload"
        else (path_on_host, path_on_board)
    )
    board = get_device_by_name("board")
    host = get_device_by_name(which_host)
    board.nw_utility.scp(
        host.ipaddr,
        host.port,
        host.username,
        host.password,
        src,
        dst,
        action=action,
    )


def get_traceroute_from_board(host_ip, version="", options="") -> str:
    """Runs the Traceroute command on board console to a host ip and returns the route packets take to a network host

    Args:
        host_ip (str): ip address of the host
        version (str): Version of the traceroute command. Defaults to "".
        options (str): Additional options in the command. Defaults to "".

    Returns:
        dict: Return the entire route to the host ip from linux device
    """
    board = get_device_by_name("board")
    return board.nw_utility.traceroute_host(host_ip)


def parse_icmp_trace(
    device: Union[DebianLAN, DebianWAN, DebianWifi], fname: str
) -> List[ICMPPacketData]:
    """Reads and Filters out the ICMP packets from the pcap file with fields
    Source, Destinationa and Code of Query Type

    :param device: Object of the device class where tcpdump is captured
    :type device: Union[DebianLAN, DebianWAN, DebianWifi]
    :param fname: Name of the captured pcap file
    :type fname: str
    :return: Sequence of ICMP packets filtered from captured pcap file
    :rtype: List[ICMPPacketData]
    """
    out = (
        device.tshark_read_pcap(
            fname, additional_args="-Y icmp -T fields -e ip.src -e ip.dst -e icmp.type"
        )
        .split("This could be dangerous.")[-1]
        .splitlines()[1:]
    )
    output: List[ICMPPacketData] = []
    for line in out:
        try:
            (src, dst, query_code) = line.split("\t")
        except ValueError:
            raise UseCaseFailure("ICMP packets not found")

        output.append(
            ICMPPacketData(
                IPAddresses(ip_address(src), None, None)
                if type(ip_address(src)) == IPv4Address
                else IPAddresses(None, ip_address(src), None),
                IPAddresses(ip_address(dst), None, None)
                if type(ip_address(dst)) == IPv4Address
                else IPAddresses(None, ip_address(dst), None),
                int(query_code),
            )
        )
    return output


def is_icmp_packet_present(
    captured_sequence: List[ICMPPacketData], expected_sequence: List[ICMPPacketData]
) -> bool:
    """Checks whether the expected ICMP sequence matches with the captured sequence or not

    :param captured_sequence: Sequence of ICMP packets filtered from captured pcap file
    :type captured_sequence: List[ICMPPacketData]
    :param expected_sequence: Example for IPv4 source and destination and query_code as 8(Echo Request)
                            [
                                ICMPPacketData(
                                    IPAddresses(IPv4Address("172.25.1.109"),None,None),
                                    IPAddresses(IPv4Address("192.168.178.22"),None,None),
                                    8
                                ),
                            ]
    :type expected_sequence: List[ICMPPacketData]
    :return: Return True if ICMP expected sequences matches with the captured sequence else False
    :rtype: bool
    """
    last_check = 0
    final_result = []
    for icmp_packet_expected in expected_sequence:
        for i in range(last_check, len(captured_sequence)):
            if captured_sequence[i] == icmp_packet_expected:
                last_check = i
                logger.info(
                    colored(
                        f"Verified ICMP packet:\t{icmp_packet_expected.source}\t-->>\t{icmp_packet_expected.destination}\tType: {icmp_packet_expected.query_code}",
                        color="green",
                    )
                )
                final_result.append(True)
                break
        else:
            logger.info(
                colored(
                    f"Couldn't verify ICMP packet:\t{icmp_packet_expected.source}\t-->>\t{icmp_packet_expected.destination}\tType: {icmp_packet_expected.query_code}",
                    color="red",
                )
            )
            final_result.append(False)
    return all(final_result)


def is_client_ip_in_pool(
    pool_bounds: Tuple[ipaddress.IPv4Address, ipaddress.IPv4Address],
    client: Union[DebianLAN, DebianWifi, DebianWAN],
) -> bool:
    """Check for client ip in ip pool.

    :param pool_bounds: lowest and highest ip from dhcp pool
    :type pool_bounds: Tuple[ipaddress.IPv4Address, ipaddress.IPv4Address]
    :param device: devices which are to be check
    :type device: Union[DebianLAN, DebianWifi, DebianWAN]
    :return: True if lan/wifilan ip is lowest in pool range
    :rtype: bool
    """
    lan_ip_address = ipaddress.IPv4Address(
        client.get_interface_ipaddr(client.iface_dut)
    )
    ip_range = ip_pool_to_list(*pool_bounds)
    return lan_ip_address in ip_range


def set_static_ip_from_rip_config(
    ip_address: IPv4Address, client: Union[DebianLAN, DebianWifi]
) -> None:
    """Set static ip for lan, wifiLan clients based on ripv2 configs

    :param ip_address: ip address to be assigned to client interface
    :type ip_address: IPv4Address
    :param client: lan or wifiLan client for which it is required to set static ip
    :type client: Union[DebianLAN, DebianWifi]
    """
    board = get_device_by_name("board")
    rip_interface_ip, subnet = board.get_rip_iface_configs()
    client.set_static_ip(client.iface_dut, ip_address, subnet.netmask)
    client.set_default_gw(rip_interface_ip, client.iface_dut)


def resolve_dns(
    host: Union[DebianLAN, DebianWAN, DebianWifi], domain_name: str
) -> List[Dict[str, Any]]:
    """perform dig command in the devices to resolve dns

    :param host: host where the dig command has to be run
    :type host: Union[DebianLAN, DebianWAN,DebianWifi]
    :param domain_name: domain name which needs lookup
    :type domain_name: str
    :return: returns Dig output from jc parser
    :rtype: List[Dict[str, Any]]
    """
    dig_command_output = host.check_output(f"dig {domain_name}")
    result = jc.parsers.dig.parse(dig_command_output.split(";", 1)[-1])
    if result:
        return result
    else:
        raise UseCaseFailure(f"Failed to resolve {domain_name}")


def dhcp_renew_ipv4_and_get_ipv4(host: Union[DebianLAN, DebianWifi]) -> IPv4Address:
    """release and renew ipv4 in the device and return IPV4

    :param host: host where the ip has to be renewed
    :type host:  Union[DebianLAN,DebianWifi]
    :return: ipv4 address of the device
    :rtype: IPv4Address
    :raises: UseCaseFailure
    """
    try:
        host.release_dhcp(host.iface_dut)
        host.renew_dhcp(host.iface_dut)
        return host.get_interface_ipaddr(host.iface_dut)
    except PexpectErrorTimeout as e:
        raise UseCaseFailure(f"Unable to get the IPv4 address due to {e}")


def dhcp_renew_stateful_ipv6_and_get_ipv6(
    host: Union[DebianLAN, DebianWifi]
) -> IPv6Address:
    """release and renew stateful ipv6 in the device and return IPV6

    :param host: host where the ip has to be renewed
    :type host:  Union[DebianLAN,DebianWifi]
    :return: ipv6 address of the device
    :rtype: IPv6Address
    :raises: UseCaseFailure
    """
    try:
        host.release_ipv6(host.iface_dut)
        host.renew_ipv6(host.iface_dut)
        return host.get_interface_ip6addr(host.iface_dut)
    except (PexpectErrorTimeout, BftIfaceNoIpV6Addr) as e:
        raise UseCaseFailure(f"Unable to get the IPv6 address due to {e}")


def dhcp_renew_ipv6_stateless_and_get_ipv6(
    host: Union[DebianLAN, DebianWifi]
) -> IPv6Address:
    """release and renew stateless ipv6 in the device and return IPV6

    :param host: host where the ip has to be renewed
    :type host:  Union[DebianLAN,DebianWifi]
    :return: ipv6 address of the device
    :rtype: IPv6Address
    :raises: UseCaseFailure
    """
    try:
        host.release_ipv6(host.iface_dut, stateless=True)
        host.set_link_state(host.iface_dut, "down")
        host.set_link_state(host.iface_dut, "up")
        host.renew_ipv6(host.iface_dut, stateless=True)
        return host.get_interface_ip6addr(host.iface_dut)
    except (PexpectErrorTimeout, BftIfaceNoIpV6Addr) as e:
        raise UseCaseFailure(f"Unable to get the IPv6 address due to {e}")
