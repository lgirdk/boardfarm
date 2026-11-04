"""A real pexpect console spawning ``cat``, for terminal tests."""

from __future__ import annotations

from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class CatConsole(BoardfarmPexpect):
    """Minimal ``BoardfarmPexpect`` session whose child is ``cat``.

    The PTY echoes what is sent and ``cat`` repeats each line, so every input
    line comes back twice.
    """

    def __init__(self, session_name: str) -> None:
        """Spawn ``cat``.

        :param session_name: pexpect session name
        :type session_name: str
        """
        super().__init__(session_name, "cat", save_console_logs="", args=[])

    def execute_command(self, command: str, timeout: int = -1) -> str:
        """Send a line and return what ``cat`` printed back.

        :param command: line to send
        :type command: str
        :param timeout: expect timeout; -1 uses the spawn default
        :type timeout: int
        :return: the console output after the echoed command
        :rtype: str
        """
        self.sendline(command)
        self.expect_exact(command, timeout=timeout)
        self.expect(self.linesep, timeout=timeout)
        return self.get_last_output()
