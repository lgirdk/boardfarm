"""Generic Template for Line Termination Systems.

Acts as a boilerplate to further extend templating of different
broadband LTSs like CMTS, OLT or DSLAMs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LTS(ABC):  # pylint: disable=R0903
    """Generic LTS template."""

    @abstractmethod
    def tshark_read_pcap(
        self,
        fname: str,
        additional_args: str | None = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file.

        :param fname: name of the file in which captures are saved
        :param additional_args: additional arguments for tshark command
        :param timeout: time out for tshark command to be executed, defaults to 30
        :param rm_pcap: If True remove the packet capture file after reading it
        :return: return tshark read command console output
        """
        raise NotImplementedError
