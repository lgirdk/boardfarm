import pexpect
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper


class Ser2NetConnection:
    """Allow telnet and tcp sessions to be established with a \
    unit's serial ports by ser2net daemon.

    If a board is connected serially to a server running ser2net daemon, this class can be used
    to connect to the board.
    """

    def __init__(self, device=None, conn_cmd=None, **kwargs):
        """Initialize the class instance to open a pexpect session.

        :param device: device to connect, defaults to None
        :type device: object
        :param conn_cmd: conn_cmd to connect to device, defaults to None
        :type conn_cmd: string
        :param ``**kwargs``: args to be used
        :type ``**kwargs``: dict
        """
        self.device = device
        self.conn_cmd = conn_cmd
        self.device.conn_cmd = conn_cmd

    def connect(self):
        """Connect to the board/station using telnet.

        This method spawn a pexpect session with telnet command.
        The telnet port must be as per the ser2net configuration file in order to connect to
        serial ports of the board.

        :raises: Exception Board is in use (connection refused). / Password required and not supported
        """
        bft_pexpect_helper.spawn.__init__(
            self.device, command="/bin/bash", args=["-c", self.conn_cmd]
        )

        try:
            result = self.device.expect(
                [
                    "assword:",
                    "ser2net.*\r\n",
                    "OpenGear Serial Server",
                    "to access the port escape menu",
                ]
            )
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")
        if result == 0:
            raise Exception("Password required and not supported")

    def close(self, force=True):
        """Close the connection."""
        try:
            if "telnet" in self.conn_cmd:
                self.sendcontrol("]")
                self.sendline("q")
            else:
                self.sendline("~.")
        except Exception:
            self.sendline("~.")
        finally:
            super(type(self), self).close()
