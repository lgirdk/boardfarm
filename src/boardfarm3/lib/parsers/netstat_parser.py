"""Parse netstat command lines output into dataframes."""

import collections
from io import BytesIO
from typing import Any

from pandas import DataFrame

# flake8: noqa


# pylint: disable=too-few-public-methods
class NetstatParser:
    """Parse netstat command lines output into dataframes."""

    def __init__(self) -> None:
        """Initialize the NetstatParser."""
        self._inet_connections: list[str] = []

    def parse_netstat_output(self, output: str) -> DataFrame:
        """Parse given netstat output.

        :param output: netstat output
        :type output: str
        :raises ValueError: on invalid netstat output
        :return: parsed netstat output in pandas.DataFrame
        :rtype: DataFrame
        """
        sample_bytes = bytes(output, "utf-8")
        file_out = BytesIO(sample_bytes)
        value = file_out.readline()[:5].decode("utf-8")
        counter = 0
        while "Proto" not in value:
            header = file_out.readline()
            value = header[:5].decode("utf-8")
            counter += 1
            if counter == 20:
                msg = "Invalid netstat output"
                raise ValueError(msg)
        val = file_out.readlines()
        for line in val:
            if "Active UNIX domain sockets" in str(line):
                break
            inet_header, result = self._parse_inet_connection(line, header)
            if result:
                self._inet_connections.append(result)
        return DataFrame(self._inet_connections, columns=inet_header)

    # TODO: Rewrite this complex function
    # pylint: disable-next=inconsistent-return-statements,too-many-branches,too-many-locals
    def _parse_inet_connection(  # noqa: C901, RUF100
        # ruff is not aware of C901, RUF100 is needed for coexistence
        self,
        line: bytes,
        header: bytes,
        sep: str = " ",
    ) -> tuple[list[str], Any]:
        lines = line.decode("utf-8").split(sep)
        headers = header.decode("utf-8").split(sep)
        fields = [it.replace("\r\n", "") for it in lines if it not in [sep, "", "\r\n"]]
        fields1 = [
            it1.replace("-", "")
            for it1 in headers
            if it1 != " " and it1 != "" and it1 not in "\r\n"
        ]

        fields1 = [
            word for word in fields1 if word not in "Address" and word not in "name"
        ]

        dict_val = {}
        inet_header: list[str] = []
        for val in fields1:
            if val == "Foreign":
                inet_header.extend(("ForeignAddress", "ForeignPort"))
            elif val == "Local":
                inet_header.extend(("LocalAddress", "LocalPort"))
            elif val == "PID/Program":
                inet_header.extend(("PID", "Program"))
            else:
                inet_header.append(val)
        inet_connection = collections.namedtuple(  # type: ignore
            "inet_connection",
            inet_header,
        )
        try:  # pylint: disable=too-many-nested-blocks
            if not fields:
                return  # type: ignore
            for idx in range(len(fields1)):  # pylint: disable=consider-using-enumerate
                if fields1[idx] in ["Local", "Foreign"]:
                    portpos = fields[idx].rfind(":")
                    dict_val[fields1[idx] + "Address"] = fields[idx][:portpos]
                    dict_val[fields1[idx] + "Port"] = fields[idx][portpos + 1 :]
                elif fields[0].upper() == "UDP" and fields1[idx] == "State":
                    dict_val["State"] = ""
                elif "PID" in fields1[idx]:
                    if fields[0].upper() == "UDP":
                        idx = idx - 1
                    dict_val["PID"], dict_val["Program"] = fields[idx].split("/")
                else:
                    dict_val[fields1[idx].replace("-", "")] = fields[idx]
            return inet_header, inet_connection(**dict_val)
        except Exception as e:
            msg = f"Problem in parsing the output for the line {lines}!!!"
            raise ValueError(
                msg,
            ) from e
