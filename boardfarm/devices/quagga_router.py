"""Quagga router device class."""
import atexit
import logging

from boardfarm.devices import connection_decider, linux
from boardfarm.exceptions import ConnectionRefused

logger = logging.getLogger("bft")


class QuaggaRouter(linux.LinuxDevice):
    """Linux based Quagga router.

    Class should not be instantiated directly in test cases.
    This class only be used for readonly operations or tcpdump
    """

    model = "Quagga router"
    name = "quagga_router"
    prompt = [r"[\w-]{2,18}\@.*:.*\#"]
    router_prompt = "Zebra>"
    iface_dut = "cm"
    telnet_router_instance = "telnet localhost 2601"
    telnet_passwd = "Quagga"

    def __init__(self, ipaddr: str, port: str, username: str, password: str):
        """Instance initialization."""
        self.router_connection = None
        self.quagga_router_ip = ipaddr
        self.quagga_router_port = port
        self.username = username
        self.password = password
        self.connect()
        atexit.register(self.logout)

    def __repr__(self):
        """Return string format object name.

        :return: object name representation
        :rtype: string
        """
        return f"QuaggaRouter(ipaddr={self.quagga_router_ip},port={self.quagga_router_port}, usrname={self.username}, password={self.password})"

    def connect(self):
        """Create Quagga router connection

        :raises Exception: ConnectionRefused
        """
        conn_cmd = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {self.username}@{self.quagga_router_ip} -p {self.quagga_router_port}"
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
        """Logout of the Quagga router"""
        if self.isalive():
            self.sendcontrol("c")
            self.kill_console_at_exit()

    def ip_route(self) -> str:
        """Execute ip router command and parse the output.

        :return: ip route command output
        :rtype: str
        """

        ip_route_command = "show ip route"
        self.sendline(self.telnet_router_instance)
        self.expect("Password:")
        self.sendline(self.telnet_passwd)
        self.expect(self.router_prompt)
        self.sendline(ip_route_command)
        self.expect(self.router_prompt)
        ip_routes = self.before
        self.sendcontrol("]")
        self.sendline("q")
        self.expect("Connection closed.")
        return ip_routes
