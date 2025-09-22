"""RIPv2 Use Cases library.

All Use Cases are independent of the device.
"""

from __future__ import annotations

from datetime import datetime
from ipaddress import IPv4Address, ip_interface
from typing import TYPE_CHECKING

from dateutil import tz  # type: ignore[import-untyped]

from boardfarm3.exceptions import UseCaseFailure
from boardfarm3.lib.dataclass.packets import RIPv2PacketData

if TYPE_CHECKING:
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN


def parse_rip_trace(  # pylint: disable=too-many-locals
    dev: LAN | WAN,
    fname: str,
    frame_time: bool,
    rm_pcap: bool,
) -> list[RIPv2PacketData]:
    """Read and filter RIP packets from the captured file.

    The Routing Information Protocol is one of a family of IP Routing
    protocols. RIP is a simple vector routing protocol.
    This usecase parses RIP protocol packets.

    .. code-block:: python

        # example usage
        cmts_packet_cap = read_rip_trace(
            device=LanClient, fname="some_capture.pcap", frame_time=False, rm_pcap=False
        )

    .. hint:: This Use Case implements statements from the test suite such as:

        - Check that CPE is sending and receiving RIPv2 route advertisements to the CMTS
        - Verify that CPE is sending RIPv2 route advertisements every 30 seconds.

    :param dev: device where captures were taken, LAN, WAN
    :type dev: LAN | WAN
    :param fname: PCAP file to be read
    :type fname: str
    :param frame_time: If True stores timestap value in RIPv2PacketData else stores None
    :type frame_time: bool
    :param rm_pcap: if True remove the PCAP file after reading else keeps the file
    :type rm_pcap: bool
    :raises UseCaseFailure: when no RIPv2 trace is found in PCAP file
    :return: list of RIP packets as

        .. code-block:: python

            [
                (
                    frame,
                    src ip,
                    dst ip,
                    rip contact,
                    rip msg:media_attribute:connection:info,
                    time
                )
            ]

    :rtype: List[RIPv2PacketData]
    """
    output = []
    time_field = "-e frame.time_epoch" if frame_time else ""
    fields = (
        f" -Y rip -T fields -e ip.src -e ip.dst -e rip.ip -e rip.netmask {time_field}"
    )
    filter_str = fields
    raw_rip_packets = dev.tshark_read_pcap(
        fname=fname,
        additional_args=filter_str,
        rm_pcap=rm_pcap,
    )
    rip_packets = raw_rip_packets.split("This could be dangerous.\r\n")[-1]
    if not rip_packets:
        msg = f"No trace found in PCAP file {fname} with filters: {filter_str}"
        raise UseCaseFailure(msg)

    ftime = None
    for packet in rip_packets.splitlines():
        packet_fields = packet.split("\t")
        try:
            (
                src,
                dst,
                advertised_ips,
                netmask,
            ) = packet_fields[:4]

            if frame_time:
                ftime = datetime.fromtimestamp(
                    float(packet_fields[-1]),
                    tz=tz.tzlocal(),
                )

        except (IndexError, ValueError) as exception:
            msg = f"No RIPv2 trace found in PCAP file {fname}"
            raise UseCaseFailure(msg) from exception

        if advertised_ips:
            output.append(
                RIPv2PacketData(
                    source=IPv4Address(src),
                    destination=IPv4Address(dst),
                    ip_address=[IPv4Address(ip) for ip in advertised_ips.split(",")],
                    subnet=[ip_interface(mask) for mask in netmask.split(",")],
                    frame_time=ftime,
                ),
            )
    return output
