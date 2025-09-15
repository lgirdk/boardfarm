"""SSH connection module."""

from __future__ import annotations

from typing import Any

import pexpect

from boardfarm3.exceptions import BoardfarmException, DeviceConnectionError
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect

_CONNECTION_ERROR_THRESHOLD = 2
_CONNECTION_FAILED_STR: str = "Connection failed to SSH server"


class SSHConnection(BoardfarmPexpect):
    """Connect to a device via SSH."""

    def __init__(  # pylint: disable=too-many-arguments  # noqa: PLR0913
        self,  # pylint: disable=unused-argument
        name: str,
        ip_addr: str,
        username: str,
        shell_prompt: list[str],
        port: int = 22,
        password: str | None = None,
        save_console_logs: str = "",
        **kwargs: dict[str, Any],  # ignore other arguments  # noqa: ARG002
    ) -> None:
        """Initialize SSH connection.

        :param name: connection name
        :type name: str
        :param ip_addr: ip address
        :type ip_addr: str
        :param username: ssh username
        :type username: str
        :param shell_prompt: shell prompt pattern
        :type shell_prompt: list[str]
        :param port: port number, defaults to 22
        :type port: int
        :param password: password, defaults to None
        :type password: str
        :param save_console_logs: save console logs, defaults to ""
        :type save_console_logs: str
        :param kwargs: other keyword arguments
        """
        self._shell_prompt = shell_prompt
        self._username = username
        self._password = password
        args = [
            f"{username}@{ip_addr}",
            f"-p {port}",
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            "-o ServerAliveInterval=60",
            "-o ServerAliveCountMax=10",
            "-o IdentitiesOnly=yes",
            "-o HostKeyAlgorithms=+ssh-rsa",
        ]
        super().__init__(name, "ssh", save_console_logs, args)

    async def login_to_server_async(self, password: str | None = None) -> None:
        """Login to SSH session.

        :param password: ssh password
        :raises DeviceConnectionError: connection failed to SSH server
        """
        if password is None:
            password = self._password
        if await self.expect(
            ["password:", pexpect.EOF, pexpect.TIMEOUT],
            async_=True,
        ):
            raise DeviceConnectionError(_CONNECTION_FAILED_STR)
        self.sendline(password)
        if (
            await self.expect(
                [
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                    *self._shell_prompt,
                ],
                async_=True,
            )
            < _CONNECTION_ERROR_THRESHOLD
        ):
            raise DeviceConnectionError(_CONNECTION_FAILED_STR)

    def login_to_server(self, password: str | None = None) -> None:
        """Login to SSH session.

        :param password: ssh password
        :raises DeviceConnectionError: connection failed to SSH server
        """
        if password is None:
            password = self._password
        if self.expect(
            ["password:", pexpect.EOF, pexpect.TIMEOUT],
        ):
            raise DeviceConnectionError(_CONNECTION_FAILED_STR)
        self.sendline(password)
        if (
            self.expect(
                [
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                    *self._shell_prompt,
                ],
            )
            < _CONNECTION_ERROR_THRESHOLD
        ):
            raise DeviceConnectionError(_CONNECTION_FAILED_STR)

    def execute_command(self, command: str, timeout: int = -1) -> str:
        """Execute a command in the SSH session.

        :param command: command to execute
        :param timeout: timeout in seconds. defaults to -1
        :returns: command output
        """
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self.linesep)
        self.expect(self._shell_prompt, timeout=timeout)
        return self.get_last_output()

    async def execute_command_async(self, command: str, timeout: int = -1) -> str:
        """Execute a command in the SSH session.

        :param command: command to execute
        :param timeout: timeout in seconds. defaults to -1
        :returns: command output
        """
        self.sendline(command)
        await self.expect_exact(command, async_=True)
        await self.expect(self.linesep, async_=True)
        await self.expect(self._shell_prompt, timeout=timeout, async_=True)
        return self.get_last_output()

    def check_output(self, cmd: str, timeout: int = 30) -> str:
        """Return an output of the command.

        :param cmd: command to execute
        :param timeout: timeout for command execute, defaults to 30
        :raises BoardfarmException: if command doesn't execute in specified timeout
        :return: command output
        """
        self.sendline("\n" + cmd)
        self.expect_exact(cmd, timeout=timeout)
        try:
            self.expect(self._shell_prompt, timeout=timeout)
        except Exception as e:
            self.sendcontrol("c")
            msg = (
                f"Command did not complete within {timeout} seconds. "
                f"{self.name} prompt was not seen."
            )
            raise BoardfarmException(
                msg,
            ) from e
        return str(self.before.strip())

    def sudo_sendline(self, cmd: str) -> None:
        """Add sudo in the sendline if username is root.

        :param cmd: command to send
        """
        if self._username != "root":
            self.sendline("sudo true")
            password_requested = self.expect(
                [*self._shell_prompt, "password for .*:", "Password:"],
            )
            if password_requested:
                self.sendline(self._password)
                self.expect(self._shell_prompt)
            cmd = "sudo " + cmd
        self.sendline(cmd)
