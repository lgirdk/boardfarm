"""SSH connection module."""


from typing import Any, Dict, List

import pexpect

from boardfarm.exceptions import DeviceConnectionError
from boardfarm.lib.boardfarm_pexpect import BoardfarmPexpect


class SSHConnection(BoardfarmPexpect):
    """Connect to a device via SSH."""

    def __init__(
        self,  # pylint: disable=unused-argument
        name: str,
        ip_addr: str,
        username: str,
        shell_prompt: List[str],
        port: int = 22,
        password: str = None,
        **kwargs: Dict[str, Any],  # ignore other arguments
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
        args = [
            f"{username}@{ip_addr}",
            f"-p {port}",
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            "-o ServerAliveInterval=60",
            "-o ServerAliveCountMax=5",
        ]
        super().__init__(name, "ssh", args)
        self._login_to_server(password)

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
