"""SSH connection module."""


from typing import Any

import pexpect

from boardfarm3.exceptions import BoardfarmException, DeviceConnectionError
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class SSHConnection(BoardfarmPexpect):
    """Connect to a device via SSH."""

    def __init__(
        self,  # pylint: disable=unused-argument
        name: str,
        ip_addr: str,
        username: str,
        shell_prompt: list[str],
        port: int = 22,
        password: str = None,
        **kwargs: dict[str, Any],  # ignore other arguments
    ) -> None:
        """Initialize SSH connection.

        :param name: connection name
        :param ip_addr: ip address
        :param username: ssh username
        :param shell_prompt: shell prompt pattern
        :param port: port number, defaults to 22
        :param password: password, defaults to None
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
            "-o ServerAliveCountMax=5",
            "-o IdentitiesOnly=yes",
        ]
        super().__init__(name, "ssh", args)
        self._login_to_server(self._password)

    def _login_to_server(self, password: str) -> None:
        """Login to SSH session.

        :param password: ssh password
        """
        if password is not None:
            if self.expect(["password:", pexpect.EOF, pexpect.TIMEOUT]):
                raise DeviceConnectionError("Connection failed to SSH server")
            self.sendline(password)
        if self.expect([pexpect.EOF, pexpect.TIMEOUT] + self._shell_prompt) < 2:
            raise DeviceConnectionError("Connection failed to SSH server")

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
            raise BoardfarmException(
                f"Command did not complete within {timeout} seconds. "
                f"{self.name} prompt was not seen."
            ) from e
        return self.before.strip()

    def sudo_sendline(self, cmd: str) -> None:
        """Add sudo in the sendline if username is root.

        :param cmd: command to send
        """
        if self._username != "root":
            self.sendline("sudo true")
            password_requested = self.expect(
                self._shell_prompt + ["password for .*:", "Password:"]
            )
            if password_requested:
                self.sendline(self._password)
                self.expect(self._shell_prompt)
            cmd = "sudo " + cmd
        self.sendline(cmd)
