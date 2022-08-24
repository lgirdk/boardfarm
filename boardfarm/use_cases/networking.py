"""All APIs are independent of board under test."""
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

from boardfarm.devices.axiros_acs import AxirosACS
from boardfarm.devices.base_devices.board_templates import BoardSWTemplate
from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.devices.debian_wan import DebianWAN
from boardfarm.devices.debian_wifi import DebianWifi
from boardfarm.exceptions import (
    BftIfaceNoIpV6Addr,
    CodeError,
    PexpectErrorTimeout,
    UseCaseFailure,
)
from boardfarm.lib.common import http_service_kill, ip_pool_to_list
from boardfarm.lib.DeviceManager import get_device_by_name

from .voice import VoiceClient

logger = logging.getLogger("bft")


@dataclass
class IPAddresses:
    """This is an IP address data classes to hold IP objects or None."""

    ipv4: Optional[IPv4Address]
    ipv6: Optional[IPv6Address]
    link_local_ipv6: Optional[IPv6Address]


@dataclass
class ICMPPacketData:
    """ICMP packet data class.

    To hold all the packet information specific to ICMP packets.

    ``source`` and ``destination`` could be either ipv4 or ipv6 addresses.
    ``query_code`` defines the type of message received or sent and could be
    among the following:

        * Type 0 = Echo Reply
        * Type 8 = Echo Request
        * Type 9 = Router Advertisement
        * Type 10 = Router Solicitation
        * Type 13 = Timestamp Request
        * Type 14 = Timestamp Reply
    """

    source: IPAddresses
    destination: IPAddresses
    query_code: int


class HTTPResult:
    def __init__(self, response: str):
        self.response = response

        # Todo: Wget parsing has to be added

        def parse_response(response: str = response):
            if "Connection refused" in response or "Connection timed out" in response:
                raise UseCaseFailure(
                    f"Curl Failure due to the following reason {response}"
                )
            else:
                raw = re.findall(r"\<head.*\>", response, re.S)[0]
                code = re.findall(r"< HTTP\/.*\s(\d+)", response)[0]
                beautified_text = BeautifulSoup(raw, "html.parser").prettify()
                return raw, code, beautified_text

        self.raw, self.code, self.beautified_text = parse_response(response)


@contextmanager
def start_http_server(
    device: Union[DebianLAN, DebianWifi, DebianWAN],
    port: Union[int, str],
    ip_version: Union[str, int],
) -> None:
    """Start http server on given client.

    :param device: device on which server will start
    :type device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param port: port on which the server listen for incomming connections
    :type port: Union[int, str]
    :param ip_version: IP version of server values can strictly be 4 or 6
    :type ip_version: Union[str, int]
    :raises CodeError: wrong ip_version value is given in api call
    :raises UseCaseFailure: if the port is being used by other process
    :yield: pid
    :rtype: str
    """
    pid: str = ""
    if str(ip_version) not in ["4", "6"]:
        raise CodeError(
            f"ip_version value can be 4 or 6 while given value is {ip_version}"
        )

    process_id = device.get_nw_process_pid("webfsd", str(port), ip_version)
    if process_id:
        device.kill_process(process_id, 9)  # kill forefully
    if device.get_nw_process_pid("", str(port), ip_version):
        raise UseCaseFailure(
            f"Cannot proceed to start http server as port={port} is still in use, "
            "try another port"
        )
    try:
        command_params = f"-F -p {port} -{ip_version} &"
        device.sendline(f"webfsd {command_params}")
        device.expect(device.prompt, timeout=10)
        if "Address already in use" in device.before:
            raise UseCaseFailure(
                f"Address already in use, Failed to start HTTP server on {device.name}"
            )

        pid = re.search(r"(\[\d{1,}\]\s(\d+))", device.before).group(2)
        yield pid
    finally:
        device.kill_process(pid=pid, signal=15)


@contextmanager
def start_wan_ipv6_http_server(port: int = 9001) -> str:
    """To start a WAN HTTP server.

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
    """To check if WAN HTTP server is running.

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


def http_get(
    which_client: Union[DebianLAN, DebianWifi, VoiceClient], url: str, timeout: int = 20
) -> str:
    """Check if the given HTTP server in WAN is running.

    This Use Case executes a curl command with a given timeout from the given
    client. The destination is specified by the url parameter

    :param which_client : the client from where http response is got
    :type which_client: Union[DebianWifi, VoiceClient]
    :param url : url to get the response
    :type url: string,
    :param timeout: connection timeout for the curl command in seconds
    :type timeout: integer
    :return: Http response
    :rtype: object
    """
    client = which_client._obj() if type(which_client) == VoiceClient else which_client

    client.sendline(f"curl -v --connect-timeout {timeout} {url}")
    client.expect(client.prompt, timeout=timeout + 10)
    return HTTPResult(client.before)


@contextmanager
def tcpdump_on_board(
    fname: str, interface: str, filters: str = ""
) -> Generator[str, None, None]:
    """Contextmanager to perform tcpdump on the board.

    Start ``tcpdump`` on the board console and kill it outside its scope

    :param fname: the filename or the complete path of the resource
    :type fname: str
    :param interface: interface name on which the tcp traffic will listen to
    :type interface: str
    :param filters: Additional filters for the tcpdump command, defaults to ""
    :type filters: str, optional
    :yield: Yields the process id of the tcp capture started
    :rtype: Generator[str, None, None]
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
    """Read the tcpdump packets and delete the capture file afterwards.

    :param fname: filename or the complete path of the pcap file
    :type fname: str
    :param protocol: protocol to filter, defaults to ""
    :type protocol: str, optional
    :param opts: _description_, defaults to ""
    :type opts: str, optional
    :param rm_pcap: _description_, defaults to True
    :type rm_pcap: bool, optional
    :return: Output of tcpdump read command
    :rtype: str
    """
    board = get_device_by_name("board")
    return board.nw_utility.read_tcpdump(
        fname, protocol=protocol, opts=opts, rm_pcap=rm_pcap
    )


def perform_scp_action_on_board(
    path_on_board: str, path_on_host: str, which_host: str, action: str
) -> None:
    """Copy files and directories between the board and the remote host.

    Copy is made over SSH.

    :param path_on_board: Path on the board
    :type path_on_board: str
    :param path_on_host: Path on the remote host
    :type path_on_host: str
    :param which_host: name of the remote host i.e lan, lan2, wan
    :type which_host: str
    :param action: scp action to perform i.e upload, download
    :type action: str
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
    """Run the ``traceroute`` on board console.

    Returns the route packets take to a network host.

    :param host_ip: IP address of the host
    :type host_ip: :str
    :param version: Version of the traceroute command, defaults to ""
    :type version: str, optional
    :param options: Additional options in the command, defaults to ""
    :type options: str, optional
    :return: Return the entire route to the host IP from linux device
    :rtype: str
    """
    board = get_device_by_name("board")
    return board.nw_utility.traceroute_host(host_ip)


def parse_icmp_trace(
    device: Union[DebianLAN, DebianWAN, DebianWifi], fname: str
) -> List[ICMPPacketData]:
    """Read and Filter out the ICMP packets from the pcap file with fields.

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
    """Check whether the expected ICMP sequence matches with the captured sequence.

    :param captured_sequence: Sequence of ICMP packets filtered from captured pcap file
    :type captured_sequence: List[ICMPPacketData]
    :param expected_sequence: Example for IPv4 source and destination and ``query_code``
        as 8 (Echo Request)

            .. code-block:: python

                [
                    ICMPPacketData(
                        IPAddresses(IPv4Address("172.25.1.109"),None,None),
                        IPAddresses(IPv4Address("192.168.178.22"),None,None),
                        8
                    ),
                ]

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
    """Check for client IP in IP pool.

    :param pool_bounds: lowest and highest IP from dhcp pool
    :type pool_bounds: Tuple[ipaddress.IPv4Address, ipaddress.IPv4Address]
    :param device: devices which are to be check
    :type device: Union[DebianLAN, DebianWifi, DebianWAN]
    :return: True if lan/wifilan IP is lowest in pool range
    :rtype: bool
    """
    lan_ip_address = ipaddress.IPv4Address(
        client.get_interface_ipaddr(client.iface_dut)
    )
    ip_range = ip_pool_to_list(*pool_bounds)
    return lan_ip_address in ip_range


def set_static_ip_from_rip_config(
    ip_address: IPv4Address, client: Union[DebianLAN, DebianWifi], rip_iface_index: int
) -> None:
    """Set static IP for lan, wifiLan clients based on ripv2 configs.

    :param ip_address: IP address to be assigned to client interface
    :type ip_address: IPv4Address
    :param rip_iface_index: index of rIP interface, value can be 1 or 4
        [1 for erouter0 and 4 for primary lan]
    :type rip_iface_index: int
    :param client: lan or wifiLan client for which it is required to set static ip
    :type client: Union[DebianLAN, DebianWifi]
    """
    board = get_device_by_name("board")
    rip_interface_ip, subnet = board.get_rip_iface_configs(rip_iface_index)
    client.set_static_ip(client.iface_dut, ip_address, subnet.netmask)
    client.set_default_gw(rip_interface_ip, client.iface_dut)


def resolve_dns(
    host: Union[DebianLAN, DebianWAN, DebianWifi], domain_name: str
) -> List[Dict[str, Any]]:
    """Perform ``dig`` command in the devices to resolve DNS.

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
    """Release and renew ipv4 in the device and return IPV4.

    :param host: host where the IP has to be renewed
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
    """Release and renew stateful ipv6 in the device and return IPV6.

    :param host: host where the IP has to be renewed
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
    """Release and renew stateless ipv6 in the device and return IPV6.

    :param host: host where the IP has to be renewed
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


def block_ipv4_traffic(
    device: Union[DebianWAN, AxirosACS, BoardSWTemplate],
    destination: Union[str, IPv4Address],
) -> None:
    """Block the traffic to and from the destination address.

    :param device: device class object
    :type device: Union[DebianLAN, DebianWAN, DebianWifi, AxirosACS, BoardSWTemplate]
    :param destination: destination IP or the corresponding domain name to be blocked
    :type destination: Union[str,IPv4Address]
    """
    device.firewall.add_drop_rule_iptables("-s", destination)
    device.firewall.add_drop_rule_iptables("-d", destination)


def block_ipv6_traffic(
    device: Union[DebianWAN, AxirosACS, BoardSWTemplate],
    destination: Union[str, IPv6Address],
) -> None:
    """Block the traffic to and from the destination address.

    :param device: device class object
    :type device: Union[DebianLAN, DebianWAN, DebianWifi, AxirosACS, BoardSWTemplate]
    :param destination: destination IP or the corresponding domain name to be blocked
    :type destination: Union[str,IPv6Address]
    """
    device.firewall.add_drop_rule_ip6tables("-s", destination)
    device.firewall.add_drop_rule_ip6tables("-d", destination)


def unblock_ipv4_traffic(
    device: Union[DebianWAN, AxirosACS, BoardSWTemplate],
    destination: Union[str, IPv4Address],
) -> None:
    """Unblock the traffic to and from the destination address on a device.

    :param device: device class object
    :type device: Union[DebianLAN, DebianWAN, DebianWifi, AxirosACS, BoardSWTemplate]
    :param destination: destination IP or the corresponding domain name to be unblocked
    :type destination: Union[str,IPv4Address]
    """
    device.firewall.del_drop_rule_iptables("-s", destination)
    device.firewall.del_drop_rule_iptables("-d", destination)


def unblock_ipv6_traffic(
    device: Union[DebianWAN, AxirosACS, BoardSWTemplate],
    destination: Union[str, IPv6Address],
) -> None:
    """Unblock the traffic to and from the destination address.

    :param device: device class object
    :type device: Union[DebianLAN, DebianWAN, DebianWifi, AxirosACS, BoardSWTemplate]
    :param destination: destination IP or the corresponding domain name to be unblocked
    :type destination: Union[str,IPv6Address]
    """
    device.firewall.del_drop_rule_ip6tables("-s", destination)
    device.firewall.del_drop_rule_ip6tables("-d", destination)
