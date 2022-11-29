"""ser2net connection module."""
import pexpect

from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect

# pylint: disable=duplicate-code


class Ser2NetConnection(BoardfarmPexpect):
    """Allow telnet session to be established the ser2net daemon.

    Requires the ser2net deamon to be running. Configuration to be stored in
    /etc/ser2net.conf
    Several devices can be connected to a host without the need of a terminal
    server. The following is a sample configuration for a single console:

    2001:telnet:0:/dev/ttyUSB0:115200 NONE 1STOPBIT 8DATABITS XONXOFF \
            banner max-connections=1

    The telnet:0 disables the timeout on the telnet session.
    No authentication needed.
    """

    def __init__(self, name: str, ip_addr: str, port: str, shell_prompt: str) -> None:
        """Initialize the class instance to open a pexpect session.

        :param name: the session name
        :type name: str
        :param ip_addr: IP address (usually, but not always, "localhost")
        :type ip_addr: str
        :param port: the telnet port
        :type port: str
        :param shell_prompt: shell prompt to expect
        :type shell_prompt: str
        :raises DeviceConnectionError: on failure to connect
        """
        self._shell_prompt = shell_prompt
        self._ip_addr = ip_addr
        self._port = port
        self._shell_prompt = shell_prompt
        super().__init__(name, "telnet", [ip_addr, port])
        if self.expect([f"ser2net port {port}", pexpect.TIMEOUT], timeout=10):
            raise DeviceConnectionError(
                f"ser2net: Failed to run 'telnet {ip_addr} {port}'"
            )

    def execute_command(self, command: str, timeout: int = 30) -> str:
        """Execute a command in the SSH session.

        :param command: command to be executed
        :type command: str
        :param timeout: timeout for command execute, defaults to 30
        :type timeout: int
        :return: command output
        :rtype: str
        """
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self._shell_prompt, timeout=timeout)
        return self.get_last_output()

    def close(self, force: bool = True) -> None:
        """Close the connection.

        :param force: True to send a SIGKILL, False for SIGINT/UP, default True
        :type force: bool
        """
        self.sendcontrol("]")
        self.sendline("q")
        super().close(force=force)
