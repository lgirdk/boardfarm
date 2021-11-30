"""All APIs are independent of board under test.
"""
import re
from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from typing import Generator, Optional, Union

import pexpect
from bs4 import BeautifulSoup

from boardfarm.exceptions import UseCaseFailure
from boardfarm.lib.common import http_service_kill
from boardfarm.lib.DeviceManager import get_device_by_name

from .voice import VoiceClient
from .wifi import WifiClient


@dataclass
class IPAddresses:
    """This is an IP address data classes to hold ip objects or None."""

    ipv4: Optional[IPv4Address]
    ipv6: Optional[IPv6Address]


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


def http_get(which_client: Union[WifiClient, VoiceClient], url: str) -> str:
    """To check if wan http server is running.
    :param which_client : the client from where http response is got
    :type which_client: Union[WifiClient, VoiceClient]
    :param url : url to get the response
    :type url: string
    :return: Http response
    :rtype: object
    """
    which_client._obj().sendline(f"curl -v {url}")
    which_client._obj().expect(which_client._obj().prompt)
    return HTTPResult(which_client._obj().before)


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


def remove_resource_from_board(fname: str):
    """Removes the file from the board console

    Args:
        fname (str): the filename or the complete path of the resource
    """
    board = get_device_by_name("board")
    board.linux_console_utility.remove_resource(fname)


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
