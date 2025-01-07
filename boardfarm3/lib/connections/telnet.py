"""Telnet connection module."""

from __future__ import annotations

import pexpect

from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class TelnetConnection(BoardfarmPexpect):
    """A simple telnet session."""

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
        :type args: list[str]
        """
        self._ip_addr, self._port, self._shell_prompt = args[0], args[1], args.pop(2)
        super().__init__(
            session_name=session_name,
            command=command,
            save_console_logs=save_console_logs,
            args=args,
        )

    async def login_to_server_async(self, password: str | None = None) -> None:
        """Login to Telnet seerver using asyncio.

        :param password: Telnet password (currently unused)
        :raises DeviceConnectionError: connection failed to Telnet server
        """
        if password is not None:
            msg = "Authenticated Telnet not supported."
            raise DeviceConnectionError(msg)
        if (
            await self.expect(
                [
                    f"Connected to {self._ip_addr}",
                    "Escape character is '^]'.",
                    pexpect.TIMEOUT,
                ],
                timeout=10,
                async_=True,
            )
            > 1
        ):
            msg = f"Failed to run 'telnet {self._ip_addr} {self._port}'"
            raise DeviceConnectionError(msg)

    def login_to_server(self, password: str | None = None) -> None:
        """Login to Telnet server.

        :param password: Telnet password
        :raises DeviceConnectionError: connection failed to Telnet server
        """
        if password is not None:
            msg = "Authenticated Telnet not supported."
            raise DeviceConnectionError(msg)
        if self.expect(
            [
                f"Connected to {self._ip_addr}",
                "Escape character is '^]'.",
                pexpect.TIMEOUT,
            ],
            timeout=10,
        ):
            msg = f"Failed to run 'telnet {self._ip_addr} {self._port}'"
            raise DeviceConnectionError(
                msg,
            )

    def execute_command(self, command: str, timeout: int = 30) -> str:
        """Execute a command in the Telnet session.

        :param command: command to be executed
        :type command: str
        :param timeout: timeout for command execute, defaults to 30
        :type timeout: int
        :return: command output
        :rtype: str
        """
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self._shell_prompt, timeout=timeout)
        return self.get_last_output()

    async def execute_command_async(self, command: str, timeout: int = -1) -> str:
        """Execute a command in the Telnet session.

        :param command: command to execute
        :param timeout: timeout in seconds. defaults to -1
        :returns: command output
        """
        self.sendline(command)
        await self.expect_exact(command, async_=True)
        await self.expect(self.linesep, async_=True)
        await self.expect(self._shell_prompt, timeout=timeout, async_=True)
        return self.get_last_output()

    def close(self, force: bool = True) -> None:
        """Close the connection.

        :param force: True to send a SIGKILL, False for SIGINT/UP, default True
        :type force: bool
        """
        self.sendcontrol("]")
        self.sendline("q")
        super().close(force=force)
