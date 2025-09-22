"""ser2net connection module."""

from __future__ import annotations

import pexpect

from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.connections.telnet import TelnetConnection

# pylint: disable=duplicate-code


class Ser2NetConnection(TelnetConnection):
    """Allow telnet session to be established with the ser2net daemon.

    Requires the ser2net daemon to be running. Configuration to be stored in
    /etc/ser2net.conf
    Several devices can be connected to a host without the need for a terminal
    server. The following is a sample configuration for a single console:

    2001:telnet:0:/dev/ttyUSB0:115200 NONE 1STOPBIT 8DATABITS XONXOFF \
            banner max-connections=1

    The telnet:0 disables the timeout on the telnet session.
    No authentication needed.
    """

    def __init__(
        self,
        session_name: str,
        command: str,
        save_console_logs: str,
        args: list[str],
    ) -> None:
        """Initialize the Ser2Net connection.

        :param session_name: pexpect session name
        :type session_name: str
        :param command: command to start the pexpect session
        :type command: str
        :param save_console_logs: save console logs to disk
        :type save_console_logs: str
        :param args: additional arguments to the command
        :type args: list[str  |  list[str]]
        """
        self._ip_addr, self._port = args[0], args[1]
        super().__init__(
            session_name,
            command,
            save_console_logs,
            args,
        )

    async def login_to_server_async(self, password: str | None = None) -> None:
        """Login to Ser2Net server using asyncio.

        :param password: Telnet password
        :raises DeviceConnectionError: connection failed to Telnet server
        """
        await super().login_to_server_async(password)
        if (
            await self.expect(
                [f"ser2net port.*{self._port}", pexpect.TIMEOUT],
                timeout=10,
                async_=True,
            )
            == 1
        ):
            msg = f"ser2net: Failed to run 'telnet {self._ip_addr} {self._port}'"
            raise DeviceConnectionError(msg)

    def login_to_server(self, password: str | None = None) -> None:
        """Login to Ser2Net server.

        :param password: Telnet password
        :raises DeviceConnectionError: connection failed to Telnet server
        """
        super().login_to_server(password)
        if self.expect(
            [f"ser2net port.*{self._port}", pexpect.TIMEOUT],
            timeout=10,
        ):
            msg = f"ser2net: Failed to run 'telnet {self._ip_addr} {self._port}'"
            raise DeviceConnectionError(msg)
