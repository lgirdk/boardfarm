"""Network utilities module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from boardfarm3.lib.networking import (
    scp,
    start_tcpdump,
    stop_tcpdump,
    tcpdump_read,
    traceroute_host,
)
from boardfarm3.lib.parsers.netstat_parser import NetstatParser

if TYPE_CHECKING:
    from pandas import DataFrame

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class NetworkUtility:
    """Network utilities."""

    def __init__(self, console: BoardfarmPexpect) -> None:
        """Initialize the network utility.

        :param console: console instance which has network utilities
        :type console: BoardfarmPexpect
        """
        self._console = console

    def netstat(self, opts: str = "", extra_opts: str = "") -> DataFrame:
        """Perform netstat with given options.

        :param opts: command line options
        :type opts: str
        :param extra_opts: extra command line options
        :type extra_opts: str
        :return: parsed netstat output
        :rtype: DataFrame
        """
        return NetstatParser().parse_netstat_output(
            self._console.execute_command(f"netstat {opts} {extra_opts}")
        )

    def start_tcpdump(
        self, fname: str, interface: str, filters: dict | None = None
    ) -> str:
        """Start tcpdump capture on given interface.

        :param fname: tcpdump output file name
        :type fname: str
        :param interface: interface name to be captured
        :type interface: str
        :param filters: filters as key value pair(eg: {"-v": "", "-c": "4"})
                        default to None
        :type filters: dict | None
        :return: return the process id of the tcpdump capture
        :rtype: str
        """
        return start_tcpdump(self._console, interface, None, fname, filters)

    def stop_tcpdump(self, pid: str) -> None:
        """Stop tcpdump process with given process id.

        :param pid: tcpdump process id
        :type pid: str
        """
        stop_tcpdump(self._console, pid)

    def read_tcpdump(  # noqa: PLR0913
        self,
        capture_file: str,
        protocol: str = "",
        opts: str = "",
        timeout: int = 30,
        rm_pcap: bool = True,
    ) -> str:
        """Read tcpdump packets and delete the pcap file afterwards.

        :param capture_file: tcpdump pcap file path
        :type capture_file: str
        :param protocol: protocol to the filter
        :type protocol: str
        :param opts: command line options to tcpdump
        :type opts: str
        :param timeout: timeout for reading the tcpdump output
        :type timeout: int
        :param rm_pcap: remove pcap file after read
        :type rm_pcap: bool
        :return: tcpdump output
        :rtype: str
        """
        return tcpdump_read(
            self._console,
            capture_file,
            protocol=protocol,
            opts=opts,
            timeout=timeout,
            rm_pcap=rm_pcap,
        )

    # pylint: disable-next=too-many-arguments,invalid-name
    def scp(  # noqa: PLR0913
        self,
        ip: str,
        port: int | str,
        user: str,
        pwd: str,
        source_path: str,
        dest_path: str,
        action: Literal["download", "upload"],
    ) -> None:
        """Copy file between this device and the remote host.

        :param ip: ip address of the remote host
        :type ip: str
        :param port: port number of the remote host
        :type port: int | str
        :param user: username of the host
        :type user: str
        :param pwd: password of the host
        :type pwd: str
        :param source_path: source file path
        :type source_path: str
        :param dest_path: destination path
        :type dest_path: str
        :param action: scp action(download/upload)
        :type action: Literal["download", "upload"]
        """
        scp(
            self._console,
            host=ip,
            port=port,
            username=user,
            password=pwd,
            src_path=source_path,
            dst_path=dest_path,
            action=action,
        )

    def traceroute_host(
        self, host_ip: str, version: str = "", options: str = ""
    ) -> str:
        """Run traceroute to given host ip and return result.

        :param host_ip: ip address of the host
        :type host_ip: str
        :param version: ip address version
        :type version: str
        :param options: command line options to traceroute
        :type options: str
        :return: output of traceroute
        :rtype: str
        """
        return traceroute_host(self._console, host_ip, version=version, options=options)
