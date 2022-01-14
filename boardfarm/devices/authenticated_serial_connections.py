"""Authenticated connections to the terminal server."""
import abc

import pexpect

import boardfarm.config as config
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from boardfarm.lib.regexlib import ValidIpv4AddressRegex


class _AuthenticatedSerialConnection(metaclass=abc.ABCMeta):
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

    def _spawn(self, cmd: str) -> None:
        bft_pexpect_helper.spawn.__init__(
            self.device,
            command="/bin/bash",
            args=["-c", cmd],
        )

    @abc.abstractclassmethod
    def connect(self) -> None:
        """Connect to the board/station using telnet.

        This method spawn a pexpect session with a command.
        The derived class must implenet this method.

        :raises: Exception Board is in use (connection refused).
        """

    @abc.abstractclassmethod
    def close(self) -> None:
        """Close the connection."""
        super().close()


class AuthenticatedTelnetConnection(_AuthenticatedSerialConnection):
    """Allow authenticated telnet sessions to be established with a \
    unit's serial ports by OpenGear server.

    If a board is connected serially to a OpenGear terminal server, this class can be used
    to connect to the board.
    """

    def connect(self):
        """Connect to the board/station using telnet.

        This method spawn a pexpect session with telnet command.
        The telnet port must be as per the ser2net configuration file in order to connect to
        serial ports of the board.

        :raises: Exception Board is in use (connection refused).
        """
        self._spawn(self.conn_cmd)

        try:
            self.device.expect(["login:"])
            self.device.sendline(self.username)
            self.device.expect(["Password:"])
            self.device.setecho(False)
            self.device.sendline(self.password)
            self.device.setecho(True)
            self.device.expect(["OpenGear Serial Server"])
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")

    def close(self) -> None:
        """Close the connection."""
        try:
            self.sendcontrol("]")
            self.sendline("q")
        finally:
            super().close()


class AuthenticatedSshConnection(_AuthenticatedSerialConnection):
    """Allow authenticated ssh sessions to be established with a \
    unit's serial ports by OpenGear server.

    If a board is connected serially to a OpenGear terminal server, this class can be used
    to connect to the board.
    """

    def connect(self) -> None:
        """Connect to the board/station using telnet.

        This method spawn a pexpect session with telnet command.
        The ssh port must be as per the ser2net configuration file in order to connect to
        serial ports of the board.

        :raises: Exception Board is in use (connection refused).
        """
        if "ssh" not in self.conn_cmd:
            raise Exception(
                "ssh connection string is not found. Check inventory server or inventory.json"
            )

        self._spawn(
            self.conn_cmd + f" -l {self.username} "
            "-o StrictHostKeyChecking=No "
            "-o UserKnownHostsFile=/dev/null "
            "-o ServerAliveInterval=60 "
            "-o ServerAliveCountMax=5",
        )

        try:
            self.device.expect(["Password:"])
            self.device.setecho(False)
            self.device.sendline(self.password)
            self.device.setecho(True)
            self.device.expect(["OpenGear Serial Server"])
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")

    def close(self) -> None:
        """Close the connection."""
        try:
            self.send("\n~.")
            self.expect(f"Connection to {ValidIpv4AddressRegex} closed.")
        finally:
            super().close()
