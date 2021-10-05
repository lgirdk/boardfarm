"""All APIs are independent of board under test.
"""
import re
from contextlib import contextmanager
from typing import Union

import pexpect
from bs4 import BeautifulSoup

from boardfarm.exceptions import UseCaseFailure
from boardfarm.lib.common import http_service_kill
from boardfarm.lib.DeviceManager import get_device_by_name

from .voice import VoiceClient
from .wifi import WifiClient


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
