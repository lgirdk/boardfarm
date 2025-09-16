"""Connect to a device with a local serial command.

Basically a local command with no authentication on connection.
"""

from __future__ import annotations

import os
from typing import Any

from pexpect import EOF

from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.connections.local_cmd import LocalCmd


class SerialConnection(LocalCmd):
    """Connect to a device with local serail command.

    No authentication needed. Just connect!
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,  # pylint: disable=unused-argument
        name: str,
        conn_command: str,
        save_console_logs: str,
        shell_prompt: list[str] | None = None,
        args: list[str] | None = None,
        **kwargs: dict[str, Any],
    ) -> None:
        """Initialize local command serial connection.

        No authentication!

        :param name: connection name
        :type name: str
        :param conn_command: command to start the session
        :type conn_command: str
        :param save_console_logs: save console logs to disk
        :type save_console_logs: str
        :param shell_prompt: shell prompt pattern, defaults to None
        :type shell_prompt: list[str]
        :param args: arguments to the command, defaults to None
        :type args: list[str], optional
        :param kwargs: additional keyword args
        :raises DeviceConnectionError: on connection failure
        """
        if args is None:
            args = conn_command.split()
            conn_command = args.pop(0)
        if kwargs.get("env") is None:
            # some serial commands need a terminal that is not "dumb"
            kwargs["env"] = {
                "PATH": os.getenv("PATH"),
                "TERM": os.getenv("TERM") if os.getenv("TERM") else "xterm",
            }
        super().__init__(
            name, conn_command, save_console_logs, shell_prompt, args, **kwargs
        )
        try:
            self.expect("Terminal ready", 5)
        except EOF as exc:
            raise DeviceConnectionError(self.before) from exc

    # pylint: disable=duplicate-code
    def login_to_server(self, password: str | None = None) -> None:
        """Do not do anything, just connect.

        :param password: unused
        """

    def execute_command(self, command: str, timeout: int = -1) -> str:
        """Execute a command in the local command session.

        :param command: command to execute
        :param timeout: timeout in seconds. defaults to -1
        :returns: command output
        """
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self.linesep)
        # TODO: is this needed? is the shell prompt of Local(Jenkins or any user)?
        self.expect(self._shell_prompt, timeout=timeout)
        return self.get_last_output()

    # pylint: enable=duplicate-code
