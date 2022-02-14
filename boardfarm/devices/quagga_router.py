"""Quagga router device class."""
import atexit
import ipaddress
import logging
from typing import List

from boardfarm.devices import connection_decider, linux
from boardfarm.exceptions import ConnectionRefused

logger = logging.getLogger("bft")


class QuaggaRouter(linux.LinuxDevice):
    """Linux based Quagga router for mini cmts.

    Class should not be instantiated directly in test cases.
    This class only be used for readonly operations or tcpdump
    """

    model = "Quagga router"
    name = "quagga_router"
    prompt = [r"[\w-]{2,18}\@.*:.*\#"]
    iface_dut = "cm"

    def __init__(self, ipaddr: str, port: str, username: str, password: str):
        """Instance initialization."""
        self.router_connection = None
        self.quagga_router_ip = ipaddr
        self.quagga_router_port = port
        self.username = username
        self.password = password
        self.connect()
        atexit.register(self.logout())

    def __repr__(self):
        """Return string format object name.

        :return: object name representation
        :rtype: string
        """
        return f"QuaggaRouter(ipaddr={self.quagga_router_ip},port={self.quagga_router_port}, usrname={self.username}, password={self.password})"

    def connect(self):
        """This is for mini cmts router connection

        :raises Exception: ConnectionRefused
        """
        conn_cmd = f'ssh -o "StrictHostKeyChecking no" {self.username}@{self.quagga_router_ip} -p {self.quagga_router_port}'
        self.router_connection = connection_decider.connection(
            "local_cmd", device=self, conn_cmd=conn_cmd
        )
        try:
            self.router_connection.connect()
            self.linesep = "\r"
            if 0 == self.expect(["assword: "] + self.prompt):
                self.sendline(self.password)
                self.expect(self.prompt)
        except Exception as e:
            logger.error(e)
            raise ConnectionRefused(f"Failed to connect to SSH due to {self.before}")

    def logout(self):
        """Logout of the mini CMTS router"""
        self.router_connection.close()

    def ip_route(self) -> List[str]:
        """Execute ip router command and parse the output.

        :return: ip route command output
        :rtype: List[str]
        """
        command = "ip route list"
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self.prompt)
        routes_in_table = [
            ipaddress.ip_address(route_)
            for route_ in self.before.split("\r\n")[:-1]
            if route_
        ]
        return routes_in_table
