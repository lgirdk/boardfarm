"""Boardfarm pexpect session module."""

import re
from abc import ABCMeta, abstractmethod
from logging import Logger, getLogger

import pexpect


class _LogWrapper:
    """Wrapper to log console output."""

    # pylint: disable=C0116  # wrapper to console logging

    _chars_to_remove = re.compile(
        r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|\r|\n|\x1B[78]"
    )

    def __init__(self, logger: Logger) -> None:
        self._logger = logger
        self._lastline = ""

    def write(self, string: str) -> None:
        string = self._lastline + string
        lines: list[str] = [line for line in string.splitlines(True) if line != "\r"]
        if lines and not string.endswith("\n"):
            self._lastline = lines[-1]
            lines = lines[:-1]
        else:
            self._lastline = ""
        for line in lines:
            self._logger.debug(
                self._chars_to_remove.sub("", line).replace("\t", "  ").rstrip()
            )

    def flush(self) -> None:
        pass


class BoardfarmPexpect(pexpect.spawn, metaclass=ABCMeta):
    """Boardfarm pexpect session."""

    def __init__(
        self,
        session_name: str,
        command: str,
        args: list[str],
    ):
        """Initialize boardfarm pexpect.

        :param session_name: pexpect session name
        :param command: command to start pexpect session
        :param args: arguments to the command
        """
        super().__init__(
            command,
            args=args,
            encoding="utf-8",
            dimensions=(24, 240),
            codec_errors="ignore",
        )
        self.logfile_read = _LogWrapper(getLogger(f"pexpect.{session_name}"))

    def get_last_output(self) -> str:
        """Get last output from the buffer.

        :returns: last output from the buffer
        """
        return self.before.strip()

    @abstractmethod
    def execute_command(self, command: str, timeout: int = -1) -> str:
        """Execute a command in the pexpect session.

        :param command: command to execute
        :param timeout: timeout in seconds. Defaults to -1
        :returns: output of given command execution
        """
        raise NotImplementedError

    def start_interactive_session(self) -> None:
        """Start interactive pexpect session."""
        log_wrapper = self.logfile_read
        self.logfile_read = None
        self.interact()
        self.logfile_read = log_wrapper
