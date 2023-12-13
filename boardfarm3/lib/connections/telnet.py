"""Telnet connection module."""

import pexpect

from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class TelnetConnection(BoardfarmPexpect):
    """A simple telnet session."""

    def __init__(
        self,
        session_name: str,
        command: str,
        save_console_logs: bool,
        args: list[str],
    ) -> None:
        """Initialize the Ser2Net connection.

        :param session_name: pexpect session name
        :type session_name: str
        :param command: command to start the pexpect session
        :type command: str
        :param save_console_logs: save console logs to disk
        :type save_console_logs: bool
        :param args: additional arguments to the command
        :type args: list[str]
        :raises DeviceConnectionError: When failed to connect to device via telnet
        """
        self._ip_addr, self._port, self._shell_prompt = args[0], args[1], args.pop(2)
        super().__init__(
            session_name=session_name,
            command=command,
            save_console_logs=save_console_logs,
            args=args,
        )
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
        """Execute a command in the SSH session.

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

    def close(self, force: bool = True) -> None:
        """Close the connection.

        :param force: True to send a SIGKILL, False for SIGINT/UP, default True
        :type force: bool
        """
        self.sendcontrol("]")
        self.sendline("q")
        super().close(force=force)
