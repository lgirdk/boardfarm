import pexpect

import boardfarm.config as config
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper


class AuthenticatedTelnetConnection:
    """Allow authenticated telnet sessions to be established with a \
    unit's serial ports by OpenGear server.

    If a board is connected serially to a OpenGear terminal server, this class can be used
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
        if not config.ldap:
            raise Exception("Please, provide ldap credentials in env variables")
        self.username, self.password = config.ldap.split(";")

    def connect(self):
        """Connect to the board/station using telnet.

        This method spawn a pexpect session with telnet command.
        The telnet port must be as per the ser2net configuration file in order to connect to
        serial ports of the board.

        :raises: Exception Board is in use (connection refused).
        """
        if "telnet" not in self.conn_cmd:
            raise Exception(
                "Telnet connection string is not found. Check inventory server or ams.json"
            )
        bft_pexpect_helper.spawn.__init__(
            self.device, command="/bin/bash", args=["-c", self.conn_cmd]
        )

        try:
            self.device.expect(["login:"])
            self.device.sendline(self.username)
            self.device.expect(["Password:"])
            self.device.setecho(False)
            self.device.sendline(self.password)
            self.device.setecho(True)
            self.device.expect(["OpenGear Serial Server"])
        except Exception:
            raise
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")

    def close(self):
        """Close the connection."""
        try:
            self.sendcontrol("]")
            self.sendline("q")
        finally:
            super().close()
