"""Placeholder for all device descriptors."""
from dataclasses import dataclass
from typing import List, Optional

from boardfarm.devices.base_devices.sip_template import SIPPhoneTemplate, SIPTemplate
from boardfarm.devices.base_devices.wifi_template import WIFITemplate
from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.devices.debian_wan import DebianWAN
from boardfarm.exceptions import IndexError
from boardfarm.lib.DeviceManager import device_manager


@dataclass
class WifiClient:
    """Descriptor for WiFi devices."""

    band: str
    __obj: WIFITemplate
    network_type: str
    authentication: Optional[str] = "WPA-PSK"
    protocol: Optional[str] = "802.11n"

    def _obj(self):
        return self.__obj


@dataclass
class VoiceClient:
    """Descriptor for Voice clients."""

    name: str
    ip: str
    number: str
    __obj: SIPPhoneTemplate

    def _obj(self) -> SIPPhoneTemplate:
        return self.__obj


@dataclass
class VoiceServer:
    """Descriptor for Voice servers."""

    name: str
    ip: str
    __obj: SIPTemplate

    def _obj(self):
        return self.__obj


@dataclass
class LanClients:
    """Descriptor for LAN devices."""

    __obj: DebianLAN

    @property
    def _obj(self) -> DebianLAN:
        return self.__obj


@dataclass
class WanClients:
    """Descriptor for WAN devices."""

    # There will be more attributes added once use cases grow
    __obj: DebianWAN

    @property
    def _obj(self) -> DebianWAN:
        return self.__obj


# Adding the getters below.
def get_lan_clients(count) -> List[LanClients]:
    """Return a list of LAN client descriptors based on count."""
    devices = device_manager()
    if not 0 < count <= len(devices.lan_clients):
        raise IndexError("Invalid count provided")

    return [LanClients(obj) for obj in devices.lan_clients[:count]]


def get_wan_clients(count) -> List[WanClients]:
    """Return a list of WAN client descriptors based on count."""
    devices = device_manager()
    if not 0 < count <= len(devices.wan_clients):
        raise IndexError("Invalid count provided")

    return [WanClients(obj) for obj in devices.wan_clients[:count]]
