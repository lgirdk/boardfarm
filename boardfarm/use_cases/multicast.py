"""Multicast Use cases.

This will include connecting to a multicast stream via Iperf, ip mroute
or smcroute.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Generator, List, Optional, Tuple, Union

import pandas

from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.devices.debian_wan import DebianWAN
from boardfarm.devices.debian_wifi import DebianWifi
from boardfarm.exceptions import BFTypeError, UseCaseFailure
from boardfarm.lib.network_testing import kill_process, tcpdump_capture

IperfDevice = Union[DebianLAN, DebianWAN, DebianWifi]


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

    _data: Optional[pandas.DataFrame]

    @property
    def bandwidth(self) -> Optional[str]:
        """Return resultant bandwidth in Mbps.

        :return: resultant bandwidth, None if iperf failed
        :rtype: Optional[str]
        """
        return (
            self._data["bandwidth"].iloc[-1] / 1000000
            if self._data is not None
            else None
        )

    @property
    def total_loss(self) -> Optional[str]:
        """Return no. of datagrams lost.

        :return: resultant total loss, None if iperf failed
        :rtype: Optional[str]
        """
        return self._data["lost"].iloc[-1] if self._data is not None else None

    @property
    def result(self) -> Optional[pandas.DataFrame]:
        """Return the entire result as a dataframe.

        :return: iperf result in tablular format, None if iperf failed
        :rtype: Optional[pandas.DataFrame]
        """
        return self._data


def kill_all_iperf(device_list: List[IperfDevice]):
    """Kill all iperf session on target devices.

    This should be called for cleaning purposes.

    :param device_list: list of target devices
    :type device_list: List[IperfDevice]
    """
    for obj in device_list:
        dev = obj
        dev.sendcontrol("c")
        dev.expect_prompt()
        dev.check_output("for i in $(pgrep iperf); do kill -9 $i; done")


def _iperf_session_check(dev, multicast_address: str, port: int):
    if not ip_address(multicast_address).is_multicast:
        raise BFTypeError(f"{multicast_address} is not a multicast address")

    # check before running that there should be no iperf sessions with same port
    if dev.check_output(f"pgrep iperf -a | grep {port} | grep {multicast_address}"):
        raise UseCaseFailure(
            f"{dev.name} already has an iperf session with "
            f"port {port} and multicast address {multicast_address}"
        )


@contextmanager
def tcpdump(
    dev: IperfDevice, fname: str, filters: Optional[str] = "ip multicast"
) -> Generator[str, None, None]:
    """Start packet capture using tcpdump and kills the process at the end.

    Applies specific filter for multicast traffic only.

    .. hint::This Use Case implements statements from the test suite such as:

        - capturing packets sent from and to eRouter WAN
          and eRouter LAN interfaces

    :param dev: device object for a VoiceServer
    :type dev: IperfDevice
    :param fname: name of the pcap file to which the capture will be stored
    :type fname: str
    :param filters: additional filters for capture, defaults to "ip multicast"
    :type filters: Optional[str]
    :yield: process id
    :rtype: Generator[str, None, None]
    """
    pid: str = ""
    device = dev
    try:
        pid = tcpdump_capture(
            device,
            device.iface_dut,
            capture_file=fname,
            return_pid=True,
            additional_filters=f"-s0 {filters}",
        )
        yield pid
    finally:
        kill_process(device, process="tcpdump", pid=pid)


def _read_mcast_trace(dev: IperfDevice, fname: str) -> List[Tuple[str, ...]]:
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

    :param dev: Descriptor of iperf capable device with PCAP file
    :type dev: IperfDevice
    :param fname: PCAP file to be read
    :type fname: str
    :return: list of parsed IP multicast packets
    :rtype: List[Tuple[str, ...]]
    """
    device = dev
    cmd = f'tshark -r {fname} -E separator=, -Y "igmp or udp" '
    fields = (
        "-T fields -e ip.src -e ip.dst -e eth.src -e eth.dst "
        "-e ip.proto -e igmp.type -e igmp.record_type "
        "-e igmp.maddr -e igmp.saddr"
    )

    device.sudo_sendline(cmd + fields)
    device.expect(device.prompt)
    out = device.before.splitlines()
    for _i, o in enumerate(out):
        if "This could be dangerous." in o:
            break
    out = out[_i + 1 :]

    return [tuple(line.strip().split(",")) for line in out]


def parse_mcast_trace(
    dev: IperfDevice,
    fname: str,
    expected_sequence: List[Tuple[str, ...]],
    ip_version: int = 4,
) -> List[Tuple[str, ...]]:
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
        - IGMP message type (0x00000011 - IGMP Query, 0x00000022 - IGMP Report)
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

    :param dev: Descriptor of iperf capable device with PCAP file
    :type dev: IperfDevice
    :param fname: name of the PCAP file
    :type fname: str
    :param expected_sequence: expected sequence to match against captured sequence
    :type expected_sequence: List[Tuple[str, ...]]
    :param ip_version: IP version, defaults to 4
    :type ip_version: int
    :return: matched captured sequence against the expected sequence
    :rtype: List[Tuple[str, ...]]
    :raises ValueError: if invalid IP version is provided
    """
    if ip_version == 4:
        captured_sequence = _read_mcast_trace(dev, fname)
    elif ip_version == 6:
        captured_sequence = _read_mcast6_trace(dev, fname)
    else:
        raise ValueError(f"Invalid IP version: {ip_version}")
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
                print(
                    f"Verified IP Multicast:\t{packet[0]}--->{packet[1]},\t"
                    f"MAC: {packet[2]}--->{packet[3]}"
                )
                final_result.append(captured_sequence[i])
                break
        else:
            print(
                f"Failed IP Multicast verification:"
                f"\t{packet[0]}--->{packet[1]},\t"
                f"MAC: {packet[2]}--->{packet[3]}"
            )
            final_result.append(())
    return final_result


def _read_mcast6_trace(dev: IperfDevice, fname: str) -> List[Tuple[str, ...]]:
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

    :param dev: Descriptor of iperf capable device with PCAP file
    :type dev: IperfDevice
    :param fname: PCAP file to be read
    :type fname: str
    :return: list of parsed IP multicast packets
    :rtype: List[Tuple[str, ...]]
    """
    device = dev
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

    device.sudo_sendline(cmd + fields)
    device.expect(device.prompt)
    out = device.before.splitlines()
    for _i, o in enumerate(out):
        if "This could be dangerous." in o:
            break
    out = out[_i + 1 :]

    return [tuple(line.strip().split(",")) for line in out]
