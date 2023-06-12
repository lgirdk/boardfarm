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
import xmltodict
from bs4 import BeautifulSoup
from termcolor import colored

from boardfarm.devices.axiros_acs import AxirosACS
from boardfarm.devices.base_devices.board_templates import (
    BoardSWTemplate,
    BoardTemplate,
)
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
from boardfarm.use_cases.descriptors import AnyCPE

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


@dataclass
class IPerf3TrafficGenerator:
    """This is an IPerf3TrafficGenerator data classes.

    It holds sender/receiver devices and their process ids.
    """

    traffic_sender: Union[DebianLAN, DebianWifi, DebianWAN]
    sender_pid: int
    traffic_receiver: Union[DebianLAN, DebianWifi, DebianWAN]
    receiver_pid: int


class HTTPResult:
    """Class to save the object of parsed HTTP response."""

    def __init__(self, response: str):
        """Parse the response and save it as an instance.

        :param response: response from HTTP request
        :type response: str
        :raises UseCaseFailure: in case the response has some error
        """
        self.response = response

        # Todo: Wget parsing has to be added

        def parse_response(response: str = response):
            if "Connection refused" in response or "Connection timed out" in response:
                raise UseCaseFailure(
                    f"Curl Failure due to the following reason {response}"
                )
            else:
                raw = re.findall(r"\<(\!DOC|head).*\>", response, re.S)[0]
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
    which_client: Union[DebianLAN, DebianWifi, VoiceClient],
    url: str,
    timeout: int = 20,
    no_proxy: bool = False,
    is_insecure: bool = False,
    follow_redirects: bool = False,
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
    :param no_proxy: no_proxy option for curl command, defaults to False
    :type no_proxy: boolean
    :param is_insecure: is_insecure option for curl command, defaults to False
    :type is_insecure: boolean
    :param follow_redirects: follow_redirects option for curl command, defaults to False
    :type follow_redirects: boolean
    :return: Http response
    :rtype: object
    """
    options = ""
    if no_proxy:
        options += "--noproxy '*' "
    if is_insecure:
        options += "-k "
    if follow_redirects:
        options += "-L "
    client = which_client._obj() if type(which_client) == VoiceClient else which_client
    client.sendline(f"curl -v {options}--connect-timeout {timeout} {url}")
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
    path_on_board: str,
    path_on_host: str,
    which_host: str,
    action: str,
    port: Union[int, str] = 22,
    ipv6: bool = False,
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
    :param port: port to perform scp to
    :type port: Union[int, str]
    :param ipv6: wheter scp should be done to ipv4 or ipv6, defaults to ipv4
    :type ipv6: bool
    """
    (src, dst) = (
        (path_on_board, path_on_host)
        if action == "upload"
        else (path_on_host, path_on_board)
    )
    board = get_device_by_name("board")
    host = get_device_by_name(which_host)
    ip = (
        host.get_interface_ipaddr(host.iface_dut)
        if not ipv6
        else f"[{host.get_interface_ip6addr(host.iface_dut)}]"
    )
    board.nw_utility.scp(
        ip,
        port,
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
    host: Union[DebianLAN, DebianWAN, DebianWifi], domain_name: str, ipv6: bool = False
) -> List[Dict[str, Any]]:
    """Perform ``dig`` command in the devices to resolve DNS.

    :param host: host where the dig command has to be run
    :type host: Union[DebianLAN, DebianWAN,DebianWifi]
    :param domain_name: domain name which needs lookup
    :type domain_name: str
    :param ipv6: flag to perform ipv4 or ipv6 lookup, defaults to False
    :type ipv6: bool, optional
    :return: returns Dig output from jc parser
    :rtype: List[Dict[str, Any]]
    """
    record_type = "AAAA" if ipv6 else "A"
    dig_command_output = host.check_output(f"dig {record_type} {domain_name}")
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


def get_iptables_list(
    device: Union[DebianWAN, AxirosACS, BoardSWTemplate],
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> dict:
    """Get firewall's iptables.

    :param device: device class object
    :type device: Union[DebianWAN, AxirosACS, BoardSWTemplate]
    :param opts: options for iptables command
    :type opts: str
    :param extra_opts: extra options for iptables command, defaults to -nvL --line-number
    :type extra_opts: str
    :return: dict of iptable
    :rtype: dict
    """
    return device.firewall.get_iptables_list(opts, extra_opts)


def is_iptable_empty(
    device: Union[DebianWAN, AxirosACS, BoardSWTemplate],
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> bool:
    """Check if device's firewall iptable is empty.

    :param device: device class object
    :type device: Union[DebianWAN, AxirosACS, BoardSWTemplate]
    :param opts: options for iptables command
    :type opts: str
    :param extra_opts: extra options for iptables command, defaults to -nvL --line-number
    :type extra_opts: str
    :return: Whether iptable is empty
    :rtype: bool
    """
    return device.firewall.is_iptable_empty(opts, extra_opts)


def get_ip6tables_list(
    device: Union[DebianWAN, AxirosACS, BoardSWTemplate],
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> dict:
    """Get firewall's ip6tables.

    :param device: device class object
    :type device: Union[DebianWAN, AxirosACS, BoardSWTemplate]
    :param opts: options for iptables command
    :type opts: str
    :param extra_opts: extra options for iptables command, defaults to -nvL --line-number
    :type extra_opts: str
    :return: dict of iptable
    :rtype: dict
    """
    return device.firewall.get_ip6tables_list(opts, extra_opts)


def is_ip6table_empty(
    device: Union[DebianWAN, AxirosACS, BoardSWTemplate],
    opts: str = "",
    extra_opts: str = "-nvL --line-number",
) -> bool:
    """Check if device's firewall ip6table is empty.

    :param device: device class object
    :type device: Union[DebianWAN, AxirosACS, BoardSWTemplate]
    :param opts: options for iptables command
    :type opts: str
    :param extra_opts: extra options for iptables command, defaults to -nvL --line-number
    :type extra_opts: str
    :return: Whether iptable is empty
    :rtype: bool
    """
    return device.firewall.is_ip6table_empty(opts, extra_opts)


def send_ipv6_traffic_from_wan_to_non_existing_endpoint(
    wan_device: DebianWAN,
    sink_ip_addr: Union[str, IPv6Address, IPv4Address],
    traffic_port: int,
    time: int,
    udp_protocol: bool,
) -> IPerf3TrafficGenerator:
    """Send IPv6 data traffic from WAN client to an invalid destination address.

    :param wan_device: WAN device class object
    :type wan_device: DebianWAN
    :param sink_ip_addr: an unreachable ip address
    :type sink_ip_addr: Union[str, IPv6Address, IPv4Address]
    :param traffic_port: server port to connect to
    :type traffic_port: int
    :param time: time in seconds to transmit for
    :type time: int
    :param udp_protocol: use UDP rather than TCP, defaults to False
    :type udp_protocol: bool
    :return: IPerf3TrafficGenerator data class that holds sender/receiver
        devices and their process ids
    :rtype: IPerf3TrafficGenerator
    """
    source_pid = wan_device.start_traffic_sender(
        sink_ip_addr, traffic_port, ipv=6, udp_protocol=udp_protocol, time=time
    )
    return IPerf3TrafficGenerator(wan_device, source_pid, None, None)


def initiate_v4_traffic(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN],
    traffic_port: int,
    time: int,
    udp_protocol: bool,
    bind_sender_ip: Optional[str] = None,
    bind_receiver_ip: Optional[str] = None,
) -> IPerf3TrafficGenerator:
    """Initiate IPv4 only traffic from source device to destination device.

    Starts the iperf3 server on a traffic receiver and triggers the IPv4 only
    traffic from source device.

    :param source_device: device class object of a iperf client
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: device class object of a iperf server
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param traffic_port: server port to listen on/connect to
    :type traffic_port: int
    :param time: time in seconds to transmit for
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str, optional
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices and their process ids
    :rtype: IPerf3TrafficGenerator
    """
    dest_ip = destination_device.get_interface_ipaddr(destination_device.iface_dut)
    dest_pid = destination_device.start_traffic_receiver(
        traffic_port, ipv=4, bind_to_ip=bind_receiver_ip
    )
    if not dest_pid:
        return IPerf3TrafficGenerator(None, None, destination_device, dest_pid)
    source_pid = source_device.start_traffic_sender(
        dest_ip,
        traffic_port,
        ipv=4,
        udp_protocol=udp_protocol,
        time=time,
        bind_to_ip=bind_sender_ip,
    )
    return IPerf3TrafficGenerator(
        source_device, source_pid, destination_device, dest_pid
    )


def initiate_v6_traffic(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN],
    traffic_port: int,
    time: int,
    udp_protocol: bool,
    bind_sender_ip: Optional[str] = None,
    bind_receiver_ip: Optional[str] = None,
) -> IPerf3TrafficGenerator:
    """Initiate IPv6 only traffic from source device to destination device.

    Starts the iperf3 server on a traffic receiver and triggers the IPv6 only
    traffic from source device.

    :param source_device: device class object of a iperf client
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: device class object of a iperf server
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param traffic_port: server port to listen on/connect to
    :type traffic_port: int
    :param time: time in seconds to transmit for
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str, optional
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices and their process ids
    :rtype: IPerf3TrafficGenerator
    """
    dest_ip6 = destination_device.get_interface_ip6addr(destination_device.iface_dut)
    dest_pid = destination_device.start_traffic_receiver(
        traffic_port, ipv=6, bind_to_ip=bind_receiver_ip
    )
    if not dest_pid:
        return IPerf3TrafficGenerator(None, None, destination_device, dest_pid)
    source_pid = source_device.start_traffic_sender(
        dest_ip6,
        traffic_port,
        ipv=6,
        udp_protocol=udp_protocol,
        time=time,
        bind_to_ip=bind_sender_ip,
    )
    return IPerf3TrafficGenerator(
        source_device, source_pid, destination_device, dest_pid
    )


def initiate_bidirectional_ipv4_traffic(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN],
    traffic_port: int,
    time: int,
    udp_protocol: bool,
    bind_sender_ip: Optional[str] = None,
    bind_receiver_ip: Optional[str] = None,
) -> IPerf3TrafficGenerator:
    """Initiate bidirectional traffic from source device to destination device.

    Starts the iperf3 server on a traffic receiver and triggers the
    bidirectional IPv4 only traffic from source device.

    :param source_device: device class object of a iperf client
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: device class object of a iperf server
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param traffic_port: server port to listen on/connect to
    :type traffic_port: int
    :param time: time in seconds to transmit for
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str, optional
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices and their process ids
    :rtype: IPerf3TrafficGenerator
    """
    dest_ip = destination_device.get_interface_ipaddr(destination_device.iface_dut)
    dest_pid = destination_device.start_traffic_receiver(
        traffic_port, ipv=4, bind_to_ip=bind_receiver_ip
    )
    if not dest_pid:
        return IPerf3TrafficGenerator(None, None, destination_device, dest_pid)
    source_pid = source_device.start_traffic_sender(
        dest_ip,
        traffic_port,
        ipv=4,
        udp_protocol=udp_protocol,
        time=time,
        direction="--bidir",
        bind_to_ip=bind_sender_ip,
    )
    return IPerf3TrafficGenerator(
        source_device, source_pid, destination_device, dest_pid
    )


def initiate_bidirectional_ipv6_traffic(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN],
    traffic_port: int,
    time: int,
    udp_protocol: bool,
    bind_sender_ip: Optional[str] = None,
    bind_receiver_ip: Optional[str] = None,
) -> IPerf3TrafficGenerator:
    """Initiate bidirectional traffic from source device to destination device.

    Starts the iperf3 server on a traffic receiver and triggers the
    bidirectional IPv6 only traffic from source device.

    :param source_device: device class object of a iperf client
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: device class object of a iperf server
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param traffic_port: server port to listen on/connect to
    :type traffic_port: int
    :param time: time in seconds to transmit for
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str, optional
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices and their process ids
    :rtype: IPerf3TrafficGenerator
    """
    dest_ip = destination_device.get_interface_ip6addr(destination_device.iface_dut)
    dest_pid = destination_device.start_traffic_receiver(
        traffic_port, ipv=6, bind_to_ip=bind_receiver_ip
    )
    if not dest_pid:
        return IPerf3TrafficGenerator(None, None, destination_device, dest_pid)
    source_pid = source_device.start_traffic_sender(
        dest_ip,
        traffic_port,
        ipv=6,
        udp_protocol=udp_protocol,
        time=time,
        direction="--bidir",
        bind_to_ip=bind_sender_ip,
    )
    return IPerf3TrafficGenerator(
        source_device, source_pid, destination_device, dest_pid
    )


def initiate_downstream_ipv4_traffic(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN],
    traffic_port: int,
    time: int,
    udp_protocol: bool,
    bind_sender_ip: Optional[str] = None,
    bind_receiver_ip: Optional[str] = None,
) -> IPerf3TrafficGenerator:
    """Initiate downstream traffic from source device to destination device.

    Starts the iperf3 server on a traffic receiver and triggers the
    downstream IPv4 only traffic from source device.

    :param source_device: device class object of a iperf client
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: device class object of a iperf server
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param traffic_port: server port to listen on/connect to
    :type traffic_port: int
    :param time: time in seconds to transmit for
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str, optional
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices and their process ids
    :rtype: IPerf3TrafficGenerator
    """
    dest_ip = destination_device.get_interface_ip6addr(destination_device.iface_dut)
    dest_pid = destination_device.start_traffic_receiver(
        traffic_port, ipv=6, bind_to_ip=bind_receiver_ip
    )
    if not dest_pid:
        return IPerf3TrafficGenerator(None, None, destination_device, dest_pid)
    source_pid = source_device.start_traffic_sender(
        dest_ip,
        traffic_port,
        ipv=6,
        udp_protocol=udp_protocol,
        time=time,
        direction="--reverse",
        bind_to_ip=bind_sender_ip,
    )
    return IPerf3TrafficGenerator(
        source_device, source_pid, destination_device, dest_pid
    )


def initiate_downstream_ipv6_traffic(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN],
    traffic_port: int,
    time: int,
    udp_protocol: bool,
    bind_sender_ip: Optional[str] = None,
    bind_receiver_ip: Optional[str] = None,
) -> IPerf3TrafficGenerator:
    """Initiate downstream traffic from source device to destination device.

    Starts the iperf3 server on a traffic receiver and triggers the
    downstream IPv6 only traffic from source device.

    :param source_device: device class object of a iperf client
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: device class object of a iperf server
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param traffic_port: server port to listen on/connect to
    :type traffic_port: int
    :param time: time in seconds to transmit for
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str, optional
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices and their process ids
    :rtype: IPerf3TrafficGenerator
    """
    dest_ip = destination_device.get_interface_ip6addr(destination_device.iface_dut)
    dest_pid = destination_device.start_traffic_receiver(
        traffic_port, ipv=6, bind_to_ip=bind_receiver_ip
    )
    if not dest_pid:
        return IPerf3TrafficGenerator(None, None, destination_device, dest_pid)
    source_pid = source_device.start_traffic_sender(
        dest_ip,
        traffic_port,
        ipv=6,
        udp_protocol=udp_protocol,
        time=time,
        direction="--reverse",
        bind_to_ip=bind_sender_ip,
    )
    return IPerf3TrafficGenerator(
        source_device, source_pid, destination_device, dest_pid
    )


def stop_traffic(iperf_generator: IPerf3TrafficGenerator) -> None:
    """Stop the iprf3 processes on sender as well as receiver.

    :param iperf_generator: data class that holds sender/receiver devices and
        their process ids
    :type iperf_generator: IPerf3TrafficGenerator
    :raises UseCaseFailure: Raises the exception when either of the iperf3
        server or client processes can't be killed
    """
    sender = (
        iperf_generator.traffic_sender.stop_traffic(iperf_generator.sender_pid)
        if iperf_generator.traffic_sender and iperf_generator.sender_pid
        else None
    )

    receiver = (
        iperf_generator.traffic_receiver.stop_traffic(iperf_generator.receiver_pid)
        if iperf_generator.traffic_receiver and iperf_generator.receiver_pid
        else None
    )

    if not (sender and receiver):
        raise UseCaseFailure(
            f"Either Sender(Client) or Receiver(Server) process cannot be killed: Sender-{sender} Receiver:{receiver}"
        )


def _nmap(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE],
    ip_type: str,
    port: Optional[Union[str, int]] = None,
    protocol: Optional[str] = None,
    max_retries: Optional[int] = None,
    min_rate: Optional[int] = None,
    opts: str = None,
) -> dict:
    iface = (
        destination_device._obj.erouter_iface
        if type(destination_device) == AnyCPE
        else destination_device._obj.iface_dut
    )
    if ip_type not in ["ipv4", "ipv6"]:
        raise UseCaseFailure("Invalid ip type, should be either ipv4 or ipv6")
    ipaddr = (
        destination_device._obj.get_interface_ipaddr(iface)
        if ip_type == "ipv4"
        else f"-6 {destination_device._obj.get_interface_ip6addr(iface)}"
    )
    retries = f"-max-retries {max_retries}" if max_retries else ""
    rate = f"-min-rate {min_rate}" if min_rate else ""
    port = f"-p {port}" if port else ""
    cmd = f"nmap {protocol or ''} {port} -Pn -r {opts or ''} {ipaddr} {retries} {rate} -oX -"
    xml = source_device.check_output(cmd)
    return xmltodict.parse(xml)


def create_udp_session(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE],
    ip_type: str,
    port: Union[str, int],
    max_retries: int,
) -> dict[str, str]:
    """Create a UDP session from source to destination device on a port.

    Runs nmap network utility on source device.

    :param source_device: Source device
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: Destination device
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE]
    :param ip_type: type of ipaddress: "ipv4", "ipv6"
    :type ip_type: str
    :param port: port or range of ports: "666-999"
    :type port: Union[str, int]
    :param max_retries: maximum number retries for nmap
    :type max_retries: int, optional
    :return: xml output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return _nmap(source_device, destination_device, ip_type, port, "-sU", max_retries)


def create_tcp_session(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE],
    ip_type: str,
    port: Union[str, int],
    max_retries: int = 4,
) -> dict[str, str]:
    """Create a TCP session from source to destination device on a port.

    Runs nmap network utility on source device.

    :param source_device: Source device
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: Destination device
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE]
    :param ip_type: type of ipaddress: "ipv4", "ipv6"
    :type ip_type: str
    :param port: port or range of ports: "666-999"
    :type port: Union[str, int]
    :param max_retries: maximum number retries for nmap
    :type max_retries: int, optional
    :return: xml output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return _nmap(source_device, destination_device, ip_type, port, "-sT", max_retries)


def create_tcp_udp_session(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE],
    ip_type: str,
    port: Union[str, int],
    max_retries: int = 4,
) -> dict[str, str]:
    """Create both TCP and UDP session from source to destination device on a port.

    Runs nmap network utility on source device.

    :param source_device: Source device
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: Destination device
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE]
    :param ip_type: type of ipaddress: "ipv4", "ipv6"
    :type ip_type: str
    :param port: port or range of ports: "666-999"
    :type port: Union[str, int]
    :param max_retries: maximum number retries for nmap
    :type max_retries: int, optional
    :return: xml output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return _nmap(
        source_device, destination_device, ip_type, port, "-sU -sT", max_retries
    )


def perform_ip_flooding(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE],
    ip_type: str,
    port: Union[str, int],
    min_rate: int,
    max_retries: int = 4,
) -> dict[str, str]:
    """Perform ip flooding via nmap network utility on source device.

    :param source_device: Source device
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: Destination device
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN, AnyCPE]
    :param ip_type: type of ipaddress: "ipv4", "ipv6"
    :type ip_type: str
    :param port: port or range of ports: "666-999"
    :type port: Union[str, int]
    :param min_rate: Send packets no slower than min_rate per second
    :type min_rate: int
    :param max_retries: maximum number retries for nmap
    :type max_retries: int, optional
    :return: xml output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return _nmap(
        source_device, destination_device, ip_type, port, "-sS", max_retries, min_rate
    )


def perform_complete_scan(
    source_device: Union[DebianLAN, DebianWifi, DebianWAN],
    destination_device: Union[DebianLAN, DebianWifi, DebianWAN, BoardTemplate],
    ip_type: str,
) -> dict:
    """Perform Complete scan on destination via nmap network utility on source device.

    :param source_device: Source device
    :type source_device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param destination_device: Destination device
    :type destination_device: Union[DebianLAN, DebianWifi, DebianWAN, BoardTemplate]
    :param ip_type: type of ipaddress: "ipv4", "ipv6"
    :type ip_type: str
    :return: xml output of the nmap command in form of dictionary
    :rtype: dict[str,str]
    """
    return _nmap(source_device, destination_device, ip_type, opts="-F")


def ping(
    device: Union[DebianLAN, DebianWifi, DebianWAN, BoardTemplate],
    ping_ip: str,
    ping_count: Optional[int] = 4,
    ping_interface: Optional[str] = None,
    timeout: Optional[int] = 50,
    json_output: Optional[bool] = False,
) -> Union[bool, dict]:
    """Ping remote host ip.

    Return True if ping has 0% loss or parsed output in JSON if
    json_output=True flag is provided.

    :param device: device on which ping is performed
    :type device: Union[DebianLAN, DebianWifi, DebianWAN]
    :param ping_ip: ip to ping
    :type ping_ip: str
    :param ping_count: number of concurrent pings, defaults to 4
    :type ping_count: Optional[int]
    :param ping_interface: ping via interface, defaults to None
    :type ping_interface: Optional[str]
    :param timeout: timeout, defaults to 50
    :type timeout: Optional[int]
    :param json_output: True if ping output in dictionary format else False,
        defaults to False
    :type json_output: Optional[bool]
    :return: bool or dict of ping output
    :rtype: Union[bool, dict]
    """
    dev = device.sw.nw_utility.dev if hasattr(device, "sw") else device
    return dev.ping(
        ping_ip,
        ping_count=ping_count,
        ping_interface=ping_interface,
        timeout=timeout,
        json_output=json_output,
    )


def enable_ipv6(device: Union[DebianLAN, DebianWifi]) -> None:
    """Enable ipv6 on the connected client interface.

    The use case executes the following commands:
        - sysctl net.ipv6.conf.<interface>.disable_ipv6=0
        - sysctl net.ipv6.conf.<interface>.accept_ra=2

    :param device: LAN or WLAN device object
    :type device: Union[DebianLAN,DebianWifi]
    """
    device.enable_ipv6(device.iface_dut)
