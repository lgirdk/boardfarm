"""Miscellaneous Use Cases to interact with devices.

General tasks such as reading and setting device's date and time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from boardfarm3.exceptions import UseCaseFailure
from boardfarm3.templates.cpe import CPE

if TYPE_CHECKING:
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN


def get_device_date(device: LAN | WAN | WLAN | CPE) -> str | None:
    """Get the device's date and time.

    .. code-block:: python

        # example output
        "Friday, May 24, 2024 10:43:11"

    :param device: device from which the date and time needs to be fetched
    :type device: Union[DebianLAN, DebianWAN, DebianWifi, BoardTemplate]
    :return: date from device console
    :rtype: str | None
    """
    if isinstance(device, CPE):
        return device.sw.get_date()
    return device.get_date()


def set_device_date(device: LAN | WAN | WLAN | CPE, date: str) -> None:
    """Set the dut date and time from device console.

    :param device: device on which the date and time needs to be set
    :type device: Union[DebianLAN, DebianWAN, DebianWifi, BoardTemplate]
    :param date: value to be changed eg: Tue Dec 20 2022, 12:40:23 UTC, etc
    :type date: str
    :raises UseCaseFailure: fails the usecase if the date is not set properly
    :rtype: str
    """
    if isinstance(device, CPE):
        out = device.sw.set_date(date)
    else:
        out = device.set_date("-s", date)
    if not out:
        msg = f"Can't set the date '{date}' on '{device}'"
        raise UseCaseFailure(msg)
