"""SSH connection module."""

from __future__ import annotations

from typing import Any

import pexpect

from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.connections.ssh_connection import SSHConnection

_CONNECTION_FAILED_STR: str = "Failed to connect to device via serial"


class LdapAuthenticatedSerial(SSHConnection):
    """Connect to a serial with ldap credentials."""

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        ip_addr: str,
        ldap_credentials: str,
        shell_prompt: list[str],
        port: int = 22,
        save_console_logs: bool = False,
        **kwargs: dict[str, Any],  # ignore other arguments  # noqa: ARG002
    ) -> None:
        """Initialize ldap authenticated serial connection.

        :param name: connection name
        :type name: str
        :param ip_addr: server ip address
        :type ip_addr: str
        :param ldap_credentials: ldap credentials
        :type ldap_credentials: str
        :param shell_prompt: shell prompt patterns
        :type shell_prompt: list[str]
        :param port: port number, defaults to 22
        :type port: int
        :param save_console_logs: save console logs to disk, defaults to False
        :type save_console_logs: bool
        :param kwargs: other keyword arguments
        :raises ValueError: invalid LDAP credentials
        """
        if ";" not in ldap_credentials:
            msg = "Invalid LDAP credentials"
            raise ValueError(msg)
        username, password = ldap_credentials.split(";")
        super().__init__(
            name,
            ip_addr,
            username,
            shell_prompt,
            port,
            password,
            save_console_logs,
        )

    def login_to_server(self, password: str | None = None) -> None:
        """Login to serial server.

        :param password: LDAP password
        :type password: str
        :raises DeviceConnectionError: failed to connect to device via serial
        """
        if password is None:
            password = self._password
        if self.expect(["Password:", pexpect.EOF, pexpect.TIMEOUT]):
            raise DeviceConnectionError(_CONNECTION_FAILED_STR)
        self.sendline(password)
        if self.expect_exact(
            ["OpenGear Serial Server", pexpect.EOF, pexpect.TIMEOUT],
        ):
            raise DeviceConnectionError(_CONNECTION_FAILED_STR)

    async def login_to_server_async(self, password: str | None = None) -> None:
        """Login to serial server.

        :param password: LDAP password
        :type password: str
        :raises DeviceConnectionError: failed to connect to device via serial
        """
        if password is None:
            password = self._password
        if await self.expect(["Password:", pexpect.EOF, pexpect.TIMEOUT], async_=True):
            raise DeviceConnectionError(_CONNECTION_FAILED_STR)
        self.sendline(password)
        if await self.expect_exact(
            ["OpenGear Serial Server", pexpect.EOF, pexpect.TIMEOUT],
            async_=True,
        ):
            raise DeviceConnectionError(_CONNECTION_FAILED_STR)
