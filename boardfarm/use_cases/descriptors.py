"""Placeholder for all device descriptors."""
import re
from dataclasses import dataclass
from functools import cached_property
from typing import List

from boardfarm.devices.base_devices.acs_template import AcsTemplate
from boardfarm.devices.base_devices.board_templates import BoardTemplate
from boardfarm.devices.base_devices.sip_template import SIPPhoneTemplate, SIPTemplate
from boardfarm.devices.base_devices.wifi_template import WIFITemplate
from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.devices.debian_wan import DebianWAN
from boardfarm.exceptions import IndexError
from boardfarm.lib.DeviceManager import device_manager, device_type
from boardfarm.use_cases.wifi import get_wifi_client


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

    @cached_property
    def ip_addr(self) -> str:
        """Return the IP address on IFACE facing DUT.

        :return: IP address in string format.
        :rtype: str
        """
        return self._obj.get_interface_ipaddr(self.__obj.iface_dut)

    @cached_property
    def gw_mac_addr(self) -> str:
        """Return the L2 address of DUT gateway from ARP table.

        :return: MAC address in string format.
        :rtype: str
        """
        # must only be called post boot.
        route = self._obj.check_output("ip route show default")
        gw_ip = re.findall(r"default via (.*) dev", route)[0]
        out = self._obj.check_output(f"arp -i {self._obj.iface_dut} -a")
        return re.findall(rf"\({gw_ip}\) at\s(.*)\s\[", out)[0]

    @cached_property
    def mac_addr(self) -> str:
        """Return the L2 address of IFACE facing DUT.

        :return: MAC address in string format.
        :rtype: str
        """
        return self._obj.get_interface_macaddr(self._obj.iface_dut)


@dataclass
class WLanClients:
    """Descriptor for WLAN devices."""

    __obj: WIFITemplate

    @property
    def _obj(self) -> WIFITemplate:
        return self.__obj

    @cached_property
    def ip_addr(self) -> str:
        """Return the IP address on IFACE facing DUT.

        :return: IP address in string format.
        :rtype: str
        """
        return self._obj.get_interface_ipaddr(self.__obj.iface_dut)

    @cached_property
    def gw_mac_addr(self) -> str:
        """Return the L2 address of DUT gateway from ARP table.

        :return: MAC address in string format.
        :rtype: str
        """
        # must only be called post boot.
        route = self._obj.check_output("ip route show default")
        gw_ip = re.findall(r"default via (.*) dev", route)[0]
        out = self._obj.check_output(f"arp -i {self._obj.iface_dut} -a")
        return re.findall(rf"\({gw_ip}\) at\s(.*)\s\[", out)[0]

    @cached_property
    def mac_addr(self) -> str:
        """Return the L2 address of IFACE facing DUT.

        :return: MAC address in string format.
        :rtype: str
        """
        return self._obj.get_interface_macaddr(self._obj.iface_dut)


@dataclass
class WanClients:
    """Descriptor for WAN devices."""

    # There will be more attributes added once use cases grow
    __obj: DebianWAN

    @property
    def _obj(self) -> DebianWAN:
        return self.__obj

    @property
    def ip_addr(self) -> str:
        """Return the IP address on IFACE facing DUT Headend.

        :return: IP address in string format.
        :rtype: str
        """
        return str(self._obj.gw)


@dataclass
class ACS:
    """Descriptor for ACS device."""

    # There will be more attributes added once use cases grow
    __obj: AcsTemplate

    @property
    def _obj(self) -> AcsTemplate:
        return self.__obj


@dataclass
class AnyCPE:
    """Descriptor for Board device."""

    __obj: BoardTemplate

    @property
    def _obj(self) -> BoardTemplate:
        return self.__obj


# Adding the getters below.
def get_lan_clients(count: int) -> List[LanClients]:
    """Return a list of LAN client descriptors based on count.

    :param count: number of devices requested
    :type count: int
    :raises IndexError: if an invalid count is provided
    :return: Descriptors holding details of requested devices
    :rtype: List[LanClients]
    """
    devices = device_manager()
    if not 0 < count <= len(devices.lan_clients):
        raise IndexError("Invalid count provided")

    return [LanClients(obj) for obj in devices.lan_clients[:count]]


def get_wan_clients(count: int) -> List[WanClients]:
    """Return a list of WAN client descriptors based on count.

    :param count: number of devices requested
    :type count: int
    :raises IndexError: if an invalid count is provided
    :return: Descriptors holding details of requested devices
    :rtype: List[WanClients]
    """
    devices = device_manager()
    if not 0 < count <= len(devices.wan_clients):
        raise IndexError("Invalid count provided")

    return [WanClients(obj) for obj in devices.wan_clients[:count]]


def get_acs_descriptors(count: int) -> List[ACS]:
    """Return a list of ACS device descriptors based on count.

    :param count: number of devices requested
    :type count: int
    :raises IndexError: if an invalid count is provided
    :return: Descriptors holding details of requested devices
    :rtype: List[ACS]
    """
    devices = device_manager()
    if not 0 < count <= len(devices.acs_servers):
        raise IndexError("Invalid count provided")

    return [ACS(obj) for obj in devices.acs_servers[:count]]


def get_wlan_clients(band: float, network_type: str, count: int) -> List[WLanClients]:
    """Return a list of LAN client descriptors based on count.

    :param band: WiFi band of requested device (5.0 or 2.4)
    :type band: float
    :param network_type: Wi-Fi network type (private, guest, community)
    :type network_type: str
    :param count: number of devices requested
    :type count: int
    :raises IndexError: if an invalid count is provided
    :return: Descriptors holding details of requested devices
    :rtype: List[WLanClients]
    """
    devices = []
    for _ in range(count):
        try:
            devices.append(
                WLanClients(get_wifi_client(band=band, network_type=network_type))
            )
        except IndexError as e:
            raise IndexError("Invalid count provided") from e

    return devices


def get_board_descriptor(count: int) -> List[AnyCPE]:
    """Return a list of Board descriptors based on count.

    .. note:: At the moment count can only be 1

    :param count: no. of devices requested
    :type count: int
    :raises IndexError: if an invalid count is provided
    :return: Descriptors holding details of requested devices
    :rtype: List[AnyCPE]
    """
    # Note: The count will be more in bordfarm v3.
    if count != 1:
        raise IndexError("Invalid count provided")
    devices = device_manager()
    return [AnyCPE(devices.get_device_by_type(device_type.DUT))]
