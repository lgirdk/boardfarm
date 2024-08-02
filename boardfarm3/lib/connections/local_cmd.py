"""Connect to a device with a local command."""

from __future__ import annotations

from typing import Any

import pexpect

from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect

_CONNECTION_ERROR_THRESHOLD = 2
_CONNECTION_FAILED_STR: str = "Connection failed with Local Command"


class LocalCmd(BoardfarmPexpect):
    """Connect to a device with a local command."""

    def __init__(  # pylint: disable=too-many-arguments # noqa: PLR0913
        self,  # pylint: disable=unused-argument
        name: str,
        conn_command: str,
        save_console_logs: bool,
        shell_prompt: list[str],
        args: list[str] | None = None,
        **kwargs: dict[str, Any],  # ignore other arguments  # noqa: ARG002
    ) -> None:
        """Initialize local command connection.

        :param name: connection name
        :type name: str
        :param conn_command: command to start the session
        :type conn_command: str
        :param save_console_logs: save console logs to disk
        :type save_console_logs: bool
        :param shell_prompt: shell prompt pattern
        :type shell_prompt: list[str]
        :param args: arguments to the command, defaults to None
        :type args: list[str], optional
        :param kwargs: additional keyword args
        """
        self._shell_prompt = shell_prompt
        if args is None:
            args = []
        super().__init__(name, conn_command, save_console_logs, args)

    # pylint: disable=duplicate-code
    def login_to_server(self, password: str | None = None) -> None:
        """Login.

        :param password: ssh password
        :raises DeviceConnectionError: connection failed via local command
        """
        if password is not None:
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
        """Execute a command in the local command session.

        :param command: command to execute
        :param timeout: timeout in seconds. defaults to -1
        :returns: command output
        """
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self.linesep)
        self.expect(self._shell_prompt, timeout=timeout)
        return self.get_last_output()

    # pylint: enable=duplicate-code
