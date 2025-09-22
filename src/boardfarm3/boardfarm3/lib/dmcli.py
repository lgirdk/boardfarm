# ruff: noqa: EM102,TRY003,EM101

"""RDKB dmcli command line interface module."""

import re
from dataclasses import dataclass
from time import sleep

from boardfarm3.exceptions import BoardfarmException
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class DMCLIError(BoardfarmException):
    """Raise this on DMCLI command line utility errors."""


# pylint: disable-next=too-few-public-methods
@dataclass
class DMCLIOut:
    """DMCLI command output data.

    Properties: status, rtype, rval, console_out
    """

    status: str
    rtype: str
    rval: str
    console_out: str


class DMCLIAPI:
    """RDKB dmcli command line interface utility."""

    def __init__(self, console: BoardfarmPexpect) -> None:
        """Initialize DMCLIAPI.

        :param console: console instance which has dmcli utility
        :type console: BoardfarmPexpect
        """
        self._console = console

    def _trigger_dmcli_cmd(
        self, operation: str, param: str, sleep_timeout: float = 0.0
    ) -> DMCLIOut:
        command_output = self._console.execute_command(
            f"dmcli eRT {operation} {param}",
            timeout=60,
        )
        sleep(sleep_timeout)
        regex_match = re.search(
            r"Execution (fail|succeed)(.*)|(Can't find destination component)",
            command_output,
        )
        if not regex_match:
            raise DMCLIError("Failed to get dmcli command execution status")
        if "succeed" not in regex_match[0]:
            raise DMCLIError(f"DMCLI command execution failed: {regex_match[0]}")
        dmcli_result = DMCLIOut(regex_match[0], "", "", command_output)
        if "value:" in command_output and "getv" in operation:
            dmcli_result.rtype = re.findall(r".*type:\s*(.*),\s+", command_output).pop()
            dmcli_result.rval = re.findall(r".*value:\s*(.*) \r", command_output).pop()
        elif "is added" in command_output and "addt" in operation:
            dmcli_result.rval = re.search(rf"{param}(\d+)", command_output)[1]
            dmcli_result.rtype = "string"
        return dmcli_result

    def AddObject(self, param: str) -> DMCLIOut:  # pylint: disable=invalid-name
        """Add object via dmcli.

        :param param: param to be added
        :return: dmcli output object
        :rtype: DMCLIOut
        """
        return self._trigger_dmcli_cmd("addtable", param)

    def SPV(  # pylint: disable=invalid-name
        self,
        param: str,
        value: str,
        type_set: str = "string",
        sleep_timeout: float = 0.0,
    ) -> DMCLIOut:
        """Set given parameter via dmcli.

        :param param: param in which value is to be set
        :param value: value to be set
        :param type_set: type of value set, defaults to string
        :param sleep_timeout: sleep values when SPV, defaults to 0.0
        :return: dmcli output object
        :rtype: DMCLIOut
        """
        return self._trigger_dmcli_cmd(
            "setvalues", f"{param} {type_set} {value}", sleep_timeout
        )

    def GPV(self, param: str) -> DMCLIOut:  # pylint: disable=invalid-name
        """Get given parameter value via dmcli.

        :param param: param to get
        :type param: str
        :return: dmcli output object
        :rtype: DMCLIOut
        """
        return self._trigger_dmcli_cmd("getvalues", param)

    def DelObject(self, param: str) -> DMCLIOut:  # pylint: disable=invalid-name
        """Add object via dmcli.

        :param param: param to delete
        :return: dmcli output object
        :rtype: DMCLIOut
        """
        return self._trigger_dmcli_cmd("deltable", param)
