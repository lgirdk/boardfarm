"""Boardfarm pexpect session module."""

from __future__ import annotations

import os
import re
from abc import ABCMeta, abstractmethod
from logging import Formatter, Logger, getLogger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import pexpect

from boardfarm3.lib.utils import disable_logs


def _apply_backspace(string: str) -> str:
    while True:
        # if you find a character followed by a backspace, remove both
        char_with_backspace = re.sub(
            r"(.\x08\x1b\x5b\x4b)|(.\x08\x20\x08)",
            "",
            string,
            count=1,
        )
        if len(string) == len(char_with_backspace):
            # now remove any backspaces from beginning of the string
            return re.sub(r"(\x08\x1b\x5b\x4b)|(\x08\x20\x08)", "", char_with_backspace)
        string = char_with_backspace


class _LogWrapper:
    """Wrapper to log console output."""

    # pylint: disable=missing-docstring  # wrapper to console logging

    _chars_to_remove = re.compile(
        r"\x1B(?:[@-Z\\-_]|\[[0-?]*["
        r" -/]*[@-~])|\r|\n|\x1B[78]|\x07|(\x1b\x5b\x48\x1b\x5b\x4a)",
    )

    def __init__(self, logger: Logger) -> None:
        self._logger = logger
        self._lastline = ""

    def write(self, string: str | bytes) -> None:
        if isinstance(string, bytes):
            string = string.decode("utf-8", errors="ignore")
        string = self._lastline + string
        lines: list[str] = [line for line in string.splitlines(True) if line != "\r"]
        if lines and not string.endswith("\n"):
            self._lastline = lines[-1]
            lines = lines[:-1]
        else:
            self._lastline = ""
        for _line in lines:
            line = _apply_backspace(_line)
            self._logger.debug(
                self._chars_to_remove.sub("", line).replace("\t", "  ").rstrip(),
            )

    def flush(self) -> None:
        pass


class BoardfarmPexpect(pexpect.spawn, metaclass=ABCMeta):
    """Boardfarm pexpect session."""

    def __init__(
        self,
        session_name: str,
        command: str,
        save_console_logs: str,
        args: list[str],
        **kwargs: dict[str, Any],
    ) -> None:
        """Initialize boardfarm pexpect.

        :param session_name: pexpect session name
        :type session_name: str
        :param command: command to start pexpect session
        :type command: str
        :param save_console_logs: save console logs to the disk
        :type save_console_logs: str
        :param args: additional arguments to the command
        :type args: list[str]
        :param kwargs: may contains the 'env' for pexpect, optional
        :type kwargs: dict[str, Any]
        """
        kwargs.setdefault("env", {"PATH": os.getenv("PATH"), "TERM": "dumb"})
        super().__init__(
            command=command,
            args=list(args),
            encoding="utf-8",
            dimensions=(24, 240),
            codec_errors="ignore",
            env=kwargs.get("env"),
        )
        self._configure_logging(session_name, save_console_logs)

    def _configure_logging(self, session_name: str, save_console_logs: str) -> None:
        logger = getLogger(f"pexpect.{session_name}")
        if bool(save_console_logs):
            logs_directory = Path(save_console_logs)
            logs_directory.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                logs_directory / f"{session_name.replace('.', '_')}.txt",
                backupCount=2,
                maxBytes=25000000,
                encoding="utf-8",
            )
            handler.setFormatter(Formatter("%(asctime)s %(message)s"))
            logger.addHandler(handler)
        self.logfile_read = _LogWrapper(logger)

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
        with disable_logs("pexpect"):
            self.interact()
