"""Data classes to store all models related to network."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN


@dataclass
class IPerf3TrafficGenerator:
    """IPerf3TrafficGenerator data classes.

    It holds sender/receiver devices and their process IDs.
    """

    traffic_sender: LAN | WAN | WLAN
    sender_pid: int | None
    traffic_receiver: LAN | WAN | WLAN
    receiver_pid: int | None
    server_log_file: str = ""
    client_log_file: str = ""
