"""Data classes to store network packets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from ipaddress import IPv4Address, IPv4Interface, IPv6Interface

    from boardfarm3.lib.dataclass.interface import IPAddresses


@dataclass
class ICMPPacketData:
    """ICMP packet data class.

    To hold all the packet information specific to ICMP packets.

    ``source`` and ``destination`` could be either IPv4 or IPv6 addresses.
    ``query_code`` defines the type of message received or sent and could be
    among the following:

        * Type 0 = Echo Reply
        * Type 8 = Echo Request
        * Type 9 = Router Advertisement
        * Type 10 = Router Solicitation
        * Type 13 = Timestamp Request
        * Type 14 = Timestamp Reply
    """

    query_code: int
    source: IPAddresses
    destination: IPAddresses


@dataclass
class RIPv2PacketData:
    """Class to hold RIP packet details for Use Case."""

    source: IPv4Address
    destination: IPv4Address
    ip_address: list[IPv4Address]
    subnet: list[IPv4Interface | IPv6Interface]
    frame_time: datetime | None = None
