"""Multicast library."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from io import StringIO
from ipaddress import IPv6Address, ip_address
from time import sleep
from typing import TYPE_CHECKING, TypeAlias

import pandas as pd

from boardfarm3.exceptions import MulticastError

_LOGGER = logging.getLogger(__name__)


class MulticastGroupRecordType(Enum):
    """IGMPv3 Record Types."""

    MODE_IS_INCLUDE = 1
    MODE_IS_EXCLUDE = 2
    CHANGE_TO_INCLUDE_MODE = 3
    CHANGE_TO_EXCLUDE_MODE = 4
    ALLOW_NEW_SOURCES = 5
    BLOCK_OLD_SOURCES = 6


if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN

    IperfDevice: TypeAlias = WLAN | LAN | WAN
    IPerfDevice: TypeAlias = LAN | WAN | WLAN
    McastSource = str
    McastGroup = str
    MulticastGroupRecord = list[
        tuple[list[McastSource], McastGroup, MulticastGroupRecordType]
    ]


@dataclass
class IPerfSession:
    """Store details of IPerf session."""

    device: IperfDevice
    pid: str
    address: str
    port: int
    output_file: str


@dataclass
class IPerfStream:
    """Store details of IPerf stream."""

    device: IperfDevice
    pid: str
    address: str
    port: int
    output_file: str
    time: int = 0


@dataclass
class IPerfResult:
    """Store results of IPerf server session."""

    _data: pd.DataFrame | None

    @property
    def bandwidth(self) -> str | None:
        """Return resultant bandwidth in Mbps.

        :return: resultant bandwidth, None if iperf failed
        :rtype: Optional[str]
        """
        return (
            str(self._data["bandwidth"].iloc[-1] / 1000000)
            if self._data is not None
            else None
        )

    @property
    def total_loss(self) -> str | None:
        """Return no. of datagrams lost.

        :return: resultant total loss, None if iperf failed
        :rtype: Optional[str]
        """
        return str(self._data["lost"].iloc[-1]) if self._data is not None else None

    @property
    def result(self) -> pd.DataFrame | None:
        """Return the entire result as a dataframe.

        :return: iperf result in tablular format, None if iperf failed
        :rtype: Optional[pandas.DataFrame]
        """
        return self._data


class Multicast:
    """Multicast device component."""

    def __init__(
        self,
        device_name: str,
        iface_dut: str,
        console: BoardfarmPexpect,
        shell_prompt: list[str],
    ) -> None:
        """Initialize multicast component.

        :param device_name: device name
        :type device_name: str
        :param iface_dut: DUT interface name
        :type iface_dut: str
        :param console: console instance of the device
        :type console: BoardfarmPexpect
        :param shell_prompt: shell prompt patterns
        :type shell_prompt: list[str]
        """
        self._console = console
        self._iface_dut = iface_dut
        self._shell_prompt = shell_prompt
        self._device_name = device_name

    def kill_all_iperf_sessions(self) -> None:
        """Kill all iperf sessions."""
        self._console.sendcontrol("c")
        self._console.expect(self._shell_prompt)
        self._console.execute_command("for i in $(pgrep iperf); do kill -9 $i; done")

    def _read_mcast_ipv4_trace(self, fname: str) -> list[tuple[str, ...]]:
        """Read and filter multicast packets from the captured file.

        Multicast traffic include UDP stream packets as well as IGMP Group
        membership reports.

        IP packets will be parsed and following values are returned in a list:

            - IP source
            - IP destination
            - MAC source
            - MAC destination
            - IP protocol number (1 - ICMP, 2 - IGMP, 6 - TCP, 17 - UDP)
            - IGMP version (v3 by default)
            - IGMP Record Type number (5 - Allow new sources, 6 - Block old sources)
            - IGMP Multicast Address (if provided in group records)
            - IGMP Source Address (if provided in group records)

        :param fname: PCAP file to be read
        :type fname: str
        :return: list of parsed IP multicast packets
        :rtype: list[tuple[str, ...]]
        """
        cmd = f'tshark -r {fname} -E separator=, -Y "igmp or udp" '
        fields = (
            "-T fields -e ip.src -e ip.dst -e eth.src -e eth.dst "
            "-e ip.proto -e igmp.version -e igmp.record_type "
            "-e igmp.maddr -e igmp.saddr"
        )

        output_lines = self._console.execute_command(cmd + fields).splitlines()
        _index = 0
        for _index, line in enumerate(output_lines):
            if "This could be dangerous." in line:
                break
        results = output_lines[_index + 1:]  # fmt: skip
        return [tuple(line.strip().split(",")) for line in results]

    def _read_mcast_ipv6_trace(self, fname: str) -> list[tuple[str, ...]]:
        """Read and filter multicast packets from the captured file.

        Multicast traffic include UDP stream packets as well as MLDv2 Group
        membership reports.

        IPv6 packets will be parsed and following values are returned in a list:

            - IP source
            - IP destination
            - MAC source
            - MAC destination
            - IPv6 Next Header (0 - ICMPv6, 6 - TCP, 17 - UDP)
            - MLDv2 version (130 - MLDv2 Query, 143 - MLDv2 Report)
            - MLDv2 Record Type number (5 - Allow new sources, 6 - Block old sources)
            - MLDv2 Multicast Address (if provided in group records)
            - MLDv2 Source Address (if provided in group records)

        :param fname: PCAP file to be read
        :type fname: str
        :return: list of parsed IP multicast packets
        :rtype: list[tuple[str, ...]]
        """
        cmd = (
            f"tshark -r {fname} -E separator=, -Y "
            '"icmpv6.type==143 or icmpv6.type==130 or udp" '
        )
        fields = (
            "-T fields -e ipv6.src -e ipv6.dst -e eth.src "
            "-e eth.dst -e ipv6.nxt -e icmpv6.type "
            "-e icmpv6.mldr.mar.record_type "
            "-e icmpv6.mldr.mar.multicast_address "
            "-e icmpv6.mldr.mar.source_address"
        )
        output_lines = self._console.execute_command(cmd + fields).splitlines()
        for _index, line in enumerate(output_lines):
            if "This could be dangerous." in line:
                break
        results = output_lines[_index + 1 :]  # pylint: disable=undefined-loop-variable
        return [tuple(line.strip().split(",")) for line in results]

    def parse_mcast_trace(
        self,
        fname: str,
        expected_sequence: list[tuple[str, ...]],
        ip_version: int = 4,
    ) -> list[tuple[str, ...]]:
        """Compare captured PCAP file against an expected sequence of packets.

        This returns a matched subset of the whole packet trace.
        The sequence of the matched packets must align with expected sequence.
        The length of the matched sequence is equal to expected sequence.

        In case a packet is missing in captured sequence, an empty value is
        maintained in output at the same index as that of the expected sequence.

        IP packets in expected sequence must follow the following order:

            - IP source
            - IP destination
            - MAC source
            - MAC destination
            - IP protocol number (1 - ICMP, 2 - IGMP, 6 - TCP, 17 - UDP)
            - IGMP version (v3 by default)
            - IGMP Record Type number (5 - Allow new sources, 6 - Block old sources)
            - IGMP Multicast Address (if provided in group records)
            - IGMP Source Address (if provided in group records)

        IPv6 packets will be parsed and following values are returned in a list:

            - IPv6 source
            - IPv6 destination
            - MAC source
            - MAC destination
            - IPv6 Next Header (0 - ICMPv6, 6 - TCP, 17 - UDP)
            - MLDv2 version (130 - MLDv2 Query, 143 - MLDv2 Report)
            - MLDv2 Record Type number (5 - Allow new sources, 6 - Block old sources)
            - MLDv2 Multicast Address (if provided in group records)
            - MLDv2 Source Address (if provided in group records)

        You can use * to mark a field as Any

        .. hint:: This Use Case assists in validating statements from the
           test suite such as:

            - Check IGMPv3 report to subscribe to (S,G) from LAN on eRouter
              LAN interface
            - Check Multicast traffic from WAN multicast server is received
              on eRouter WAN interface and forwarded to Ethernet LAN client

        :param fname: name of the pcap file
        :type fname: str
        :param expected_sequence: expected sequence to match against captured sequence
        :type expected_sequence: list[tuple[str, ...]]
        :param ip_version: IP version, defaults to 4
        :type ip_version: int
        :raises ValueError: when given ip version is invalid
        :return: matched captured sequence against the expected sequence
        :rtype: list[tuple[str, ...]]
        """
        if ip_version == 4:  # noqa: PLR2004
            captured_sequence = self._read_mcast_ipv4_trace(fname)
        elif ip_version == 6:  # noqa: PLR2004
            captured_sequence = self._read_mcast_ipv6_trace(fname)
        else:
            msg = f"Invalid IP version: {ip_version}"
            raise ValueError(msg)
        last_check = 0
        final_result = []
        for packet in expected_sequence:
            for i in range(last_check, len(captured_sequence)):
                if all(
                    expected == actual
                    for expected, actual in zip(packet, captured_sequence[i])
                    if expected != "*"
                ):
                    last_check = i
                    _LOGGER.debug(
                        "Verified IP Multicast: %s--->%s, MAC: %s--->%s",
                        packet[0],
                        packet[1],
                        packet[2],
                        packet[3],
                    )
                    final_result.append(captured_sequence[i])
                    break
            else:
                _LOGGER.debug(
                    "Failed IP Multicast verification: %s--->%s, MAC: %s--->%s",
                    packet[0],
                    packet[1],
                    packet[2],
                    packet[3],
                )
                final_result.append(())
        return final_result

    def _iperf_session_check(self, multicast_address: str, port: int) -> None:
        if not ip_address(multicast_address).is_multicast:
            msg = f"{multicast_address} is not a multicast address"
            raise ValueError(msg)
        # check before running that there should be no iperf sessions with same port
        if self._console.execute_command(
            f"pgrep iperf -a | grep {port} | grep {multicast_address}",
        ):
            msg = (
                f"{self._device_name} already has an iperf session with "
                f"port {port} and multicast address {multicast_address}"
            )
            raise MulticastError(
                msg,
            )

    def join_iperf_multicast_ssm_group(
        self,
        multicast_source_addr: str,
        multicast_group_addr: str,
        port: int,
    ) -> IPerfSession:
        """Start an iperf server binding to a multicast address in background.

        This use case is applicable for SSM (source-specific multicast) channels (S,G)

        Session will have the following parameters by default:
            - 1s interval between periodic bandwidth, jitter,
              and loss reports.

        The Use Case will return an Iperf Session object holding
        following info:
        - Target device class object on which iperf command is executed
        - PID of the iperf session
        - Multicast group address
        - Multicast port
        - CSV output file of the iperf session

        .. note::

            - The multicast source will always be a WAN device.
            - CSV output file can only be accessed once you leave the multicast group.

        .. hint:: This Use Case implements statements from the test suite such as:

            - Start an Ethernet LAN client to request CPE for
              IPv4 SSM traffic from WAN multicast server
            - Start client to join/subscribe a specific source and Group (S,G)
              channel by sending IGMPv3 report

        :param multicast_source_addr: WAN IP address used to run the mcast stream
        :type multicast_source_addr: str
        :param multicast_group_addr: multicast stream's group IP address to join
        :type multicast_group_addr: str
        :param port: multicast stream's port number
        :type port: int
        :return: object holding data on the IPerf Session
        :rtype: IPerfSession
        """
        ipv6_flag = (
            "-V"
            if isinstance(ip_address(multicast_source_addr), IPv6Address)
            and isinstance(ip_address(multicast_group_addr), IPv6Address)
            else ""
        )
        # Cannot have any iperf session running for the same mul
        self._iperf_session_check(multicast_group_addr, port)
        fname = f"mclient_{port}.txt"
        # run iperf, format result as CSV
        self._console.execute_command(
            f"iperf {ipv6_flag} -s -f m -u -U -p {port} "
            f"-B {multicast_group_addr} --ssm-host {multicast_source_addr} "
            f"-i 1 -y C > {fname} &",
        )
        pid = self._console.execute_command(
            f"pgrep iperf -a | grep {port} | awk '{{print$1}}'",
        )
        return IPerfSession(None, pid, multicast_group_addr, port, fname)

    def join_iperf_multicast_asm_group(
        self,
        multicast_group_addr: str,
        port: int,
    ) -> IPerfSession:
        """Start an iperf server binding to a multicast address in background.

        This use case is applicable for ASM (any-source multicast)
        channels (*,G)  # noqa: RST213 - false positive

        Session will have the following parameters by default:
            - 1s interval between periodic bandwidth, jitter,
              and loss reports.

        The Use Case will return an Iperf Session object holding
        following info:
        - Target device class object on which iperf command is executed
        - PID of the iperf session
        - Multicast group address
        - Multicast port
        - CSV output file of the iperf session

        .. note::

            - CSV output file can only be accessed once you leave the multicast group.

        .. hint:: This Use Case implements statements from the test suite such as:

            - Start an Ethernet LAN client to request CPE for
              IPv4 ASM traffic from WAN multicast server
            - Start client to join/subscribe any source multicast channel (S,G)
              by sending IGMPv3 report

        :param multicast_group_addr: multicast stream's group IP address to join
        :type multicast_group_addr: str
        :param port: multicast stream's port number
        :type port: int
        :return: object holding data on the IPerf Session
        :rtype: IPerfSession
        """
        ipv6_flag = (
            "-V" if isinstance(ip_address(multicast_group_addr), IPv6Address) else ""
        )
        # Cannot have any iperf session running for the same mul
        self._iperf_session_check(multicast_group_addr, port)
        fname = f"mclient_{port}.txt"
        # run iperf, format result as CSV
        self._console.execute_command(
            f"iperf {ipv6_flag} -s -f m -u -U -p {port} "
            f"-B {multicast_group_addr} "
            f"-i 1 -y C > {fname} &",
        )
        pid = self._console.execute_command(
            f"pgrep iperf -a | grep {port} | awk '{{print$1}}'",
        )
        return IPerfSession(None, pid, multicast_group_addr, port, fname)

    def leave_iperf_multicast_group(self, session: IPerfSession) -> IPerfResult:
        """Send IGMP leave to stop receiving multicast traffic.

        This is achieved by stopping the iperf server bounded
        to a multicast channel ASM/SSM.

        Executes a kill -15 <iperf session pid> on target device.
        In case of IGMPv3, will send a block old sources membership report.

        :param session: session object created during the join
        :type session: IPerfSession
        :raises MulticastError: when iperf session deosn't exit
        :return: IPerf results object
        :rtype: IPerfResult
        """
        if not self._console.execute_command(
            f"pgrep iperf -a | grep {session.port}| grep {session.address}",
        ):
            # Something is wrong, there should be a process ID always.
            msg = (
                f"iperf session with port {session.port} and {session.address} "
                f"multicast group does not exist on {self._device_name}"
            )
            raise MulticastError(
                msg,
            )
        # kill -15 iperf session
        self._console.execute_command(f"kill -15 {session.pid}")
        output = self._console.execute_command(f"cat {session.output_file}")
        # remove the file after reading results
        self._console.execute_command(f"rm {session.output_file}")
        if not output.strip():
            return IPerfResult(None)

        csv = pd.read_csv(StringIO(output.strip()))
        cols = [
            "timestamp",
            "source_address",
            "source_port",
            "destination_address",
            "destination_port",
            "id",
            "interval",
            "transferred_bytes",
            "bandwidth",
            "jitter",
            "lost",
            "total",
        ]
        return IPerfResult(pd.DataFrame(csv.iloc[:, :-2].values, columns=cols))

    def start_iperf_multicast_stream(
        self,
        multicast_group_addr: str,
        port: int,
        time: int,
        bit_rate: float,
    ) -> IPerfStream:
        """Start an iperf client sending data on multicast address in background.

        Session will have the following parameters by default:
            - TTL value set to 5

        .. hint:: This Use Case implements statements from the
           test suite such as:

            - Start multicast server on WAN network to provide
              the multicast traffic in unreserved multicast group IP
              range 232.0.0.0/8
            - Start multicast server on WAN network to provide
              the multicast traffic in unreserved multicast group IP
              range FF38::8000:0/96
            - Start multicast stream on a specific Group channel
              by sending IGMPv3 report

        :param multicast_group_addr: multicast stream's group IP address
        :type multicast_group_addr: str
        :param port: multicast stream's port number
        :type port: int
        :param time: total time the session should run for
        :type time: int
        :param bit_rate: bit_rate of data to be sent (in Mbps)
        :type bit_rate: float
        :return: object holding data on the IPerf stream.
        :rtype: IPerfStream
        """
        # Ensure there is no exisiting stream with same IP and port.
        self._iperf_session_check(multicast_group_addr, port)
        ipv6_flag = (
            "-V" if isinstance(ip_address(multicast_group_addr), IPv6Address) else ""
        )
        fname = f"mserver_{port}.txt"
        self._console.execute_command(
            f"iperf {ipv6_flag} -u -f m -c {multicast_group_addr} "
            f"-p {port} --ttl 5 "
            f"-t {time} -b {bit_rate}m > {fname} &",
        )
        pid = self._console.execute_command(
            f"pgrep iperf -a | grep {port} | awk '{{print$1}}'",
        )
        return IPerfStream(None, pid, multicast_group_addr, port, fname, time)

    def wait_for_multicast_stream_to_end(self, iperf_stream: IPerfStream) -> None:
        """Wait for all multicast streams to end.

        The Use Case will wait for a time equal to the stream with
        the highest wait time.

        If a stream from the list does not exit within the
        max wait time, then throw an error.

        .. hint:: To be used along with the Use Case start_iperf_multicast_stream

        :param iperf_stream: iperf stream instance
        :type iperf_stream: IPerfStream
        :raises MulticastError: when multicast stream doesn't exit within given time
        """
        is_stream_still_running = False
        for _ in range(2):
            if not self._console.execute_command(
                f"pgrep iperf -a | grep {iperf_stream.port}| grep"
                f" {iperf_stream.address}",
            ):
                break
            sleep(1)
        else:
            is_stream_still_running = True
            self._console.execute_command(f"kill -9 {iperf_stream.pid}")
        self._console.execute_command(f"rm {iperf_stream.output_file}")
        if is_stream_still_running:
            msg = (
                f"{iperf_stream.address}:{iperf_stream.port} did not exit "
                "within {iperf_stream.time}s"
            )
            raise MulticastError(
                msg,
            )

    def send_igmpv3_report(
        self,
        mcast_group_record: MulticastGroupRecord,
        count: int,
    ) -> None:
        """Send an IGMPv3 report with desired multicast record.

        Multicast source and group must be IPv4 addresses.
        Multicast sources need to be non-multicast addresses and
        group address needs to be a multicast address.

        Implementation relies on a custom send_igmp_report
        script based on scapy.

        :param mcast_group_record: IGMPv3 multicast group record
        :type mcast_group_record: MulticastGroupRecord
        :param count: num of packets to send in 1s interval
        :type count: int
        :raises MulticastError: when failed to execute send_mld_report command
        """
        command = f"send_igmp_report -i {self._iface_dut} -c {count}"
        output = self._send_multicast_report(command, mcast_group_record)
        if f"Sent {count} packets" not in output:
            msg = f"Failed to execute send_mld_report command:\n{output}"
            raise MulticastError(
                msg,
            )

    def send_mldv2_report(
        self,
        mcast_group_record: MulticastGroupRecord,
        count: int,
    ) -> None:
        """Send an MLDv2 report with desired multicast record.

        Multicast source and group must be IPv6 addresses.
        Multicast sources need to be non-multicast addresses and
        group address needs to be a multicast address.

        Implementation relies on a custom send_mld_report
        script based on scapy.

        :param mcast_group_record: MLDv2 multicast group record
        :type mcast_group_record: MulticastGroupRecord
        :param count: num of packets to send in 1s interval
        :type count: int
        :raises MulticastError: when failed to execute send_mld_report command
        """
        command = f"send_mld_report -i {self._iface_dut} -c {count}"
        output = self._send_multicast_report(command, mcast_group_record)
        if f"Sent {count} packets" not in output:
            msg = f"Failed to execute send_mld_report command:\n{output}"
            raise MulticastError(
                msg,
            )

    def _send_multicast_report(
        self,
        command: str,
        mcast_group_record: MulticastGroupRecord,
    ) -> str:
        args = ""
        for sources, group, rtype in mcast_group_record:
            src = ",".join(sources)
            args += f'-mr "{src};{group};{rtype.value} "'
        output = self._console.execute_command(f"{command} {args}")
        if "Traceback" in output:
            msg = f"Failed to send the report!!\n{output}"
            raise MulticastError(msg)
        return output

    @property
    def gateway_mac_addr(self) -> str:
        """Return the L2 address of DUT gateway from ARP table.

        :return: MAC address in string format.
        :rtype: str
        """
        route = self._console.execute_command("ip route show default")
        gw_ip = re.findall(r"default via (.*) dev", route)[0]
        output = self._console.execute_command(f"arp -i {self._iface_dut} -a")
        return re.findall(rf"\({gw_ip}\) at\s(.*)\s\[", output)[0]
