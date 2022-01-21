# Moving getters here to provide new signatures for the tests
# Can not be placed in DevceManager.py due to circular dependencies
from typing import List

from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.devices.debian_wan import DebianWAN
from boardfarm.exceptions import IndexError
from boardfarm.lib.DeviceManager import device_manager


def get_lan_clients(count) -> List[DebianLAN]:
    """Return a list of LAN clients based on count."""
    devices = device_manager()
    if not 0 < count <= len(devices.lan_clients):
        raise IndexError(
            f"Invalid count provided. {len(devices.lan_clients)} LAN clients available"
        )

    return devices.lan_clients[:count]


def get_wan_clients(count) -> List[DebianWAN]:
    """Return a list of WAN clients based on count."""
    devices = device_manager()
    if not 0 < count <= len(devices.wan_clients):
        raise IndexError(
            f"Invalid count provided. {len(devices.lan_clients)} LAN clients available"
        )

    return devices.wan_clients[:count]
