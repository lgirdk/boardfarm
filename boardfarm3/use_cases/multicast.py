"""Multicast Use Cases.

This will include connecting to a multicast stream via iPerf, ip-mroute
or smcroute.
"""
# pylint: disable=duplicate-code  # TODO: conclude and resolve the duplicate

from __future__ import annotations

from contextlib import contextmanager
from io import StringIO
from ipaddress import IPv6Address, ip_address
from time import sleep
from typing import TYPE_CHECKING, TypeAlias

import pandas as pd

from boardfarm3.exceptions import MulticastError, UseCaseFailure
from boardfarm3.lib.multicast import IPerfResult, IPerfSession, IPerfStream

if TYPE_CHECKING:
    from collections.abc import Generator

    from boardfarm3.lib.multicast import IperfDevice
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN

    CPEClients: TypeAlias = WLAN | LAN


def _is_multicast_stream_active(
    device: IperfDevice, multicast_address: str, port: int
) -> bool:
    if not ip_address(multicast_address).is_multicast:
        msg = f"{multicast_address} is not a multicast address"
        raise MulticastError(msg)

    return bool(
        device.console.execute_command(
            f"pgrep iperf -a | grep {port} | grep {multicast_address}"
        )
    )


def kill_all_iperf(device_list: list[IperfDevice]) -> None:
    """Kill all iPerf sessions on target devices.

    This should be called for cleaning purposes.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Kill all iPerf session on target devices.

    :param device_list: list of target devices
    :type device_list: list[IPerfDevice]
    """
    for device in device_list:
        device.multicast.kill_all_iperf_sessions()


@contextmanager
def tcpdump(
    dev: IperfDevice,
    fname: str,
    filters: str | None = "ip multicast",
) -> Generator[str]:
    """Start packet capture using tcpdump and kill the process at the end.

    Applies specific filter for multicast traffic only.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Capturing packets sent from and to eRouter WAN and eRouter LAN interfaces
        - Make sure you can capture packets sent from and to eRouter WAN interface
          and Ethernet LAN client

    :param dev: LAN, WAN or WLAN device instance
    :type dev: IperfDevice
    :param fname: name of the pcap file to which the capture will be stored
    :type fname: str
    :param filters: additional filters for capture, defaults to "ip multicast"
    :type filters: str | None
    :yield: process ID
    :rtype: Generator[str, None, None]
    """
    with dev.tcpdump_capture(fname, dev.iface_dut, filters) as pid:
        yield pid


def parse_mcast_trace(
    dev: IperfDevice,
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

    .. hint:: This Use Case implements statements from the test suite such as:
       test suite such as:

        - Check IGMPv3 report to subscribe to (S,G) from LAN on eRouter
          LAN interface
        - Check Multicast traffic from WAN multicast server is received
          on eRouter WAN interface and forwarded to Ethernet LAN client

    :param dev: Descriptor of iPerf capable device with PCAP file
    :type dev: IperfDevice
    :param fname: name of the PCAP file
    :type fname: str
    :param expected_sequence: expected sequence to match against captured sequence
    :type expected_sequence: list[tuple[str, ...]]
    :param ip_version: IP version, defaults to 4
    :type ip_version: int
    :return: matched captured sequence against the expected sequence
    :rtype: list[tuple[str, ...]]
    """
    return dev.multicast.parse_mcast_trace(fname, expected_sequence, ip_version)


def join_iperf_multicast_ssm_group(
    on_which_device: IperfDevice,
    multicast_source_addr: str,
    multicast_group_addr: str,
    port: int,
) -> IPerfSession:
    """Start an iPerf server binding to a multicast address in background.

    This Use Case is applicable for SSM (source-specific multicast) channels (S,G)

    Session will have the following parameters by default:
        - 1s interval between periodic bandwidth, jitter,
          and loss reports.

    The Use Case will return an iPerf Session object holding
    following info:
    - Target device class object on which iperf command is executed
    - PID of the iperf session
    - Multicast group address
    - Multicast port
    - CSV output file of the iPerf session

    .. note::

        - The multicast source will always be a WAN device.
        - CSV output file can only be accessed once you leave the multicast group.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start an Ethernet LAN client to request CPE for
          IPv4 SSM traffic from WAN multicast server
        - Start client to join/subscribe a specific source and Group (S,G)
          channel by sending IGMPv3 report

    :param on_which_device: Object of the device that joins the mcast group
    :type on_which_device: IperfDevice
    :param multicast_source_addr: WAN IP address used to run the mcast stream
    :type multicast_source_addr: str
    :param multicast_group_addr: multicast stream's group IP address to join
    :type multicast_group_addr: str
    :param port: multicast stream's port number
    :type port: int
    :return: object holding data on the iPerf Session
    :rtype: IPerfSession
    :raises UseCaseFailure: if there is a multicat stream.
    """
    dev = on_which_device
    ipv6_flag = ""

    if isinstance(ip_address(multicast_source_addr), IPv6Address) and isinstance(
        ip_address(multicast_group_addr), IPv6Address
    ):
        ipv6_flag = "-V"

    # Cannot have any iperf session running for the same mul
    if _is_multicast_stream_active(dev, multicast_group_addr, port):
        msg = (
            f"{dev} already has an iperf session with "
            f"port {port} and multicast address {multicast_group_addr}"
        )
        raise UseCaseFailure(msg)

    fname = f"mclient_{port}.txt"

    # run iperf, format result as CSV
    dev.console.execute_command(
        f"iperf {ipv6_flag} -s -f m -u -U -p {port} "
        f"-B {multicast_group_addr} --ssm-host {multicast_source_addr} "
        f"-i 1 -y C > {fname} &"
    )

    pid = dev.console.execute_command(
        f"pgrep iperf -a | grep {port} | awk '{{print$1}}'"
    )
    return IPerfSession(on_which_device, pid, multicast_group_addr, port, fname)


def join_iperf_multicast_asm_group(
    on_which_device: IperfDevice,
    multicast_group_addr: str,
    port: int,
) -> IPerfSession:
    r"""Start an iPerf server binding to a multicast address in background.

    This Use Case is applicable for ASM (any-source multicast) channels (\*,G)

    Session will have the following parameters by default:
        - 1s interval between periodic bandwidth, jitter,
          and loss reports.

    The Use Case will return an iPerf Session object holding
    following info:
    - Target device class object on which iperf command is executed
    - PID of the iPerf session
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

    :param on_which_device: Object of the device that joins the mcast group
    :type on_which_device: IperfDevice
    :param multicast_group_addr: multicast stream's group IP address to join
    :type multicast_group_addr: str
    :param port: multicast stream's port number
    :type port: int
    :return: object holding data on the iPerf Session
    :rtype: IPerfSession
    :raises UseCaseFailure: if there is a multicat stream.
    """
    dev = on_which_device
    ipv6_flag = ""

    if isinstance(ip_address(multicast_group_addr), IPv6Address):
        ipv6_flag = "-V"

    # Cannot have any iperf session running for the same mul
    if _is_multicast_stream_active(dev, multicast_group_addr, port):
        msg = (
            f"{dev} already has an iperf session with "
            f"port {port} and multicast address {multicast_group_addr}"
        )
        raise UseCaseFailure(msg)

    fname = f"mclient_{port}.txt"

    # run iperf, format result as CSV
    dev.console.execute_command(
        f"iperf {ipv6_flag} -s -f m -u -U -p {port} "
        f"-B {multicast_group_addr} "
        f"-i 1 -y C > {fname} &"
    )

    pid = dev.console.execute_command(
        f"pgrep iperf -a | grep {port} | awk '{{print$1}}'"
    )
    return IPerfSession(on_which_device, pid, multicast_group_addr, port, fname)


def leave_iperf_multicast_group(session: IPerfSession) -> IPerfResult:
    """Send IGMP leave to stop receiving multicast traffic.

    This is achieved by stopping the iPerf server bounded
    to a multicast channel ASM/SSM.

    Executes a kill -15 <iPerf session pid> on target device.
    In case of IGMPv3, will send a block old sources membership report.

    :param session: Session object created during the join
    :type session: IPerfSession
    :return: iPerf result
    :rtype: IPerfResult
    :raises UseCaseFailure: If the device fails to leave the multicast group.
    """
    dev = session.device

    if not _is_multicast_stream_active(dev, session.address, session.port):
        # Something is wrong, there should be a process ID always.

        err_msg = (
            f"iperf session with port {session.port} "
            f"and {session.address} multicast group does "
            f"not exist on {dev}"
        )

        raise UseCaseFailure(err_msg)

    # kill -15 iperf session
    dev.console.execute_command(f"kill -15 {session.pid}")
    out = dev.console.execute_command(f"cat {session.output_file}")

    # remove the file after reading results
    dev.console.execute_command(f"rm {session.output_file}")
    if not out.strip():
        return IPerfResult(None)

    csv = pd.read_csv(StringIO(out.strip()))
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

    results = pd.DataFrame(csv.iloc[:, :-2].values, columns=cols)
    return IPerfResult(results)


def start_iperf_multicast_stream(
    on_which_device: WAN,
    multicast_group_addr: str,
    port: int,
    time: int,
    bit_rate: float,
) -> IPerfStream:
    """Start an iPerf client sending data on multicast address in background.

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

    :param on_which_device: WAN object that runs the multicast stream.
    :type on_which_device: WAN
    :param multicast_group_addr: multicast stream's group IP address
    :type multicast_group_addr: str
    :param port: multicast stream's port number
    :type port: int
    :param time: total time the session should run for
    :type time: int
    :param bit_rate: bit_rate of data to be sent (in Mbps)
    :type bit_rate: float
    :return: object holding data on the iPerf stream.
    :rtype: IPerfStream
    :raises UseCaseFailure: if there is a multicat stream.
    """
    dev = on_which_device
    ipv6_flag = ""

    if isinstance(ip_address(multicast_group_addr), IPv6Address):
        ipv6_flag = "-V"

    # Ensure there is no exisiting stream with same IP and port.
    if _is_multicast_stream_active(dev, multicast_group_addr, port):
        msg = (
            f"{dev} already has an iperf session with "
            f"port {port} and multicast address {multicast_group_addr}"
        )
        raise UseCaseFailure(msg)
    fname = f"mserver_{port}.txt"

    dev.console.execute_command(
        f"iperf {ipv6_flag} -u -f m -c {multicast_group_addr} "
        f"-p {port} --ttl 5 "
        f"-t {time} -b {bit_rate}m > {fname} &"
    )

    pid = dev.console.execute_command(
        f"pgrep iperf -a | grep {port} | awk '{{print$1}}'"
    )
    return IPerfStream(on_which_device, pid, multicast_group_addr, port, fname, time)


def wait_for_multicast_stream_to_end(stream_list: list[IPerfStream]) -> None:
    """Wait for all multicast streams to end.

    The Use Case will wait for a time equal to the stream with
    the highest wait time.

    If a stream from the list does not exit within the
    max wait time, then throw an error.

    .. hint:: To be used along with the Use Case start_iperf_multicast_stream

    :param stream_list: List of IPerfStreams
    :type stream_list: list[IPerfStream]
    :raises ValueError: if empty list is passed
    :raises UseCaseFailure: if a session fails to exit.
    """
    if not stream_list:
        msg = "Cannot pass an empty session list!"
        raise ValueError(msg)

    max_time_to_wait = max(stream.time for stream in stream_list)

    # Should expect all streams to be closed by now
    # This is not asyncio, no high expectations
    sleep(max_time_to_wait)

    failed_sessions = []
    for stream in stream_list:
        # try twice before raising exception.
        dev = stream.device
        for _ in range(2):
            if not dev.console.execute_command(
                f"pgrep iperf -a | grep {stream.port}| grep {stream.address}"
            ):
                break
            sleep(1)
        else:
            dev.console.execute_command(f"kill -9 {stream.pid}")
            failed_sessions.append(
                f"{stream.address}:{stream.port} did not exit within {stream.time}s"
            )
        dev.console.execute_command(f"rm {stream.output_file}")

    if failed_sessions:
        raise UseCaseFailure("Following sessions failed:\n".join(failed_sessions))
