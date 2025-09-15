"""Python executor module."""

from contextlib import suppress

from pexpect import TIMEOUT

from boardfarm3.exceptions import DeviceConnectionError
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class PythonExecutor:
    """Helper to execute python commands over a given Linux console."""

    def __init__(self, console: BoardfarmPexpect, shell_prompt: list[str]) -> None:
        """Initialise PythonExecutor.

        :param console: the console to execute the Python commands on
        :type console: BoardfarmPexpect
        :param shell_prompt: the console shell prompt (usually a list of regexs)
        :type shell_prompt: list[str]
        """
        self._console: BoardfarmPexpect = console
        self._shell_prompt: list[str] = shell_prompt
        self._py_prompt = ">>>"
        self._console.execute_command("kill -9 $(pgrep python3)")
        self.run("python3")

    def run(self, cmd: str, expect: str = "") -> str:
        """Run the given Python command.

        :param cmd: the Python command
        :type cmd: str
        :param expect: what to expect as output from the command, defaults to ""
        :type expect: str
        :raises DeviceConnectionError: on execution/connectivity issues
        :return: the output of the Python command
        :rtype: str
        """
        out: str = ""
        self._console.sendline(cmd)
        if not expect:
            self._console.expect(self._py_prompt)
            out = self._console.before
        else:
            self._console.expect(expect)
            out = self._console.before
            self._console.expect(self._py_prompt)

        if "Traceback" in out:
            msg = f"Failed to execute on python console command:\n{cmd}\nOutput:{out}"
            raise DeviceConnectionError(
                msg,
            )

        return out

    def exit_python(self) -> None:
        """Exit the Python prompt."""
        with suppress(TIMEOUT):
            self._console.sendcontrol("c")
            self._console.expect(self._py_prompt)
            self._console.sendcontrol("d")
            self._console.expect(self._shell_prompt)
