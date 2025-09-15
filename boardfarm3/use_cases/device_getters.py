"""Device getters use cases."""

from typing import TypeVar

from boardfarm3.exceptions import DeviceNotFound
from boardfarm3.lib.device_manager import get_device_manager
from boardfarm3.templates.lan import LAN
from boardfarm3.templates.wan import WAN

T = TypeVar("T")  # pylint: disable=invalid-name


def get_lan_clients(count: int) -> list[LAN]:
    """Return a list of LAN clients based on given count.

    :param count: number of LAN clients
    :type count: int
    :return: list of LAN clients
    :rtype: List[LAN]
    :raises DeviceNotFound: if count of LAN devices is invalid
    """
    lan_devices = get_device_manager().get_devices_by_type(
        LAN,  # type: ignore[type-abstract]
    )
    if not 0 < count <= len(lan_devices):
        msg = f"Invalid count provided. Only {len(lan_devices)} LAN clients available"
        raise DeviceNotFound(msg)
    return list(lan_devices.values())[:count]


def get_wan_clients(count: int) -> list[WAN]:
    """Return a list of WAN clients based on given count.

    :param count: number of WAN clients
    :type count: int
    :return: list of WAN clients
    :rtype: List[WAN]
    :raises DeviceNotFound: if count of WAN devices is invalid
    """
    wan_devices = get_device_manager().get_devices_by_type(
        WAN,  # type: ignore[type-abstract]
    )
    if not 0 < count <= len(wan_devices):
        msg = f"Invalid count provided. Only {len(wan_devices)} WAN clients available"
        raise DeviceNotFound(msg)
    return list(wan_devices.values())[:count]


def device_getter(device_type: type[T]) -> T:
    """Provide device of type 'device_type'.

    :param device_type: Type of device to get
    :return: Instance of device
    :raises ValueError: if no device of given type is available or
        if more than 1 device of given type is available
    """
    devs = get_device_manager().get_devices_by_type(device_type)

    if len(devs) < 1:
        msg = f"There are no {device_type} devices available"
        raise ValueError(msg)
    if len(devs) > 1:
        msg = f"More than 1 {device_type} devices found"
        raise ValueError(msg)
    return devs[next(iter(devs))]
