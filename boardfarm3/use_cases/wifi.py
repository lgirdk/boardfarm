"""Wi-Fi Use Cases library.

All APIs are independent of board under test.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from boardfarm3.lib.device_manager import get_device_manager
from boardfarm3.templates.wlan import WLAN

if TYPE_CHECKING:
    from collections.abc import Generator

    from boardfarm3.templates.cpe import CPE


def get_wifi_clients(network: str, band: str) -> list[WLAN]:
    """Return list of wlan_devices based on filters network and band type.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Return list of wlan_devices based on filters network and band type.

    :param network: network type of the client Eg: private, guest, community
    :type network: str
    :param band: band of the client in GHz
    :type band: str
    :return: list of WLAN devices
    :rtype: list[WLAN]
    """
    wifi_devices = get_device_manager().get_devices_by_type(
        WLAN,  # type: ignore[type-abstract]
    )
    return [
        device
        for device in wifi_devices.values()
        if device.network == network and device.band == band
    ]


def get_ssid(
    network: str,
    band: str,
    cpe: CPE,
    mode: str = "console",
) -> str | None:
    """Get the Wi-Fi SSID.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Get the Wi-Fi SSID.

    :param network: network type of the client E.g: private, guest, community
    :type network: str
    :param band: Wi-Fi band of the client
    :type band: str
    :param cpe: the CPE that is beaming the SSID
    :type cpe: CPE
    :param mode: way to retrieve the information, defaults to "console"
    :param mode: mode to get the SSID E.g. snmp, acs, dmcli, console (default)
    :type mode: str
    :raises NotImplementedError: not implemented for modes other than console
    :return: SSID of the Wi-Fi for a given network type and band
    :rtype: str | None
    """
    if mode == "console":
        return cpe.sw.wifi.get_ssid(network, band)
    msg = "Not implemented for modes other than console"
    raise NotImplementedError(msg)


def get_bssid(network: str, band: str, cpe: CPE, mode: str = "console") -> str | None:
    """Get the Wi-Fi Basic Service Set Identifier.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Get the Wi-Fi Basic Service Set Identifier.

    :param network: network type of the client E.g: private, guest, community
    :type network: str
    :param band: band of the client
    :type band: str
    :param cpe: the CPE that is beaming the SSID
    :type cpe: CPE
    :param mode: mode to get the BSSID. E.g. console (default), snmp, acs, dmcli
    :type mode: str
    :return: MAC physical address of the access point
    :rtype: str | None
    :raises NotImplementedError: not implemented for modes other than console
    """
    if mode == "console":
        return cpe.sw.wifi.get_bssid(network, band)
    msg = "Not implemented for modes other than console"
    raise NotImplementedError(msg)


def get_passphrase(network: str, cpe: CPE) -> str:
    """Get the Wi-Fi passphrase.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Get the Wi-Fi passphrase.

    :param network: network type of the client E.g: private, guest, community
    :type network: str
    :param cpe: the CPE that is beaming the SSID
    :type cpe: CPE
    :return: encrypted password for a network
    :rtype: str
    """
    iface = cpe.sw.wifi.wlan_ifaces[network]["5"]
    return cpe.sw.wifi.get_passphrase(iface=iface)


def connect_wifi_client(
    who_to_connect: WLAN,
    cpe: CPE,
    ssid: str | None = None,
    password: str | None = None,
    bssid: str | None = None,
) -> None:
    """Connect client to Wi-Fi.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify that the connection to 2.4GHz private Wi-Fi SSID is successful.

    :param who_to_connect: client to connect
    :type who_to_connect: WLAN
    :param cpe: the CPE to connect to
    :type cpe: CPE
    :param ssid: SSID of the network to connect
    :type ssid: str | None
    :param password: password of the network to connect
    :type password: str | None
    :param bssid: BSSID of the network to connect
    :type bssid: str | None
    """
    ssid = (
        ssid if ssid else get_ssid(who_to_connect.network, who_to_connect.band, cpe=cpe)
    )
    bssid = (
        bssid
        if bssid
        else get_bssid(who_to_connect.network, who_to_connect.band, cpe=cpe)
    )
    password = password if password else get_passphrase(who_to_connect.network, cpe=cpe)
    who_to_connect.wifi_client_connect(
        ssid_name=ssid,
        password=password,
        security_mode=who_to_connect.authentication,
        bssid=bssid,
    )


def disconnect_wifi_client(who_to_disconnect: WLAN) -> None:
    """Disconnect client from Wi-Fi.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Disconnect the client from 5GHz Wi-Fi network
        - Disconnect the client from 2.4GHz Wi-Fi network

    :param who_to_disconnect: client to disconnect
    :type who_to_disconnect: WLAN
    """
    who_to_disconnect.wifi_disconnect()


def check_and_connect_to_wifi(who_to_connect: WLAN, cpe: CPE) -> None:
    """Check if specific Wi-Fi is enabled and try to connect appropriate client.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Check if specific Wi-Fi is enabled and try to connect appropriate client.

    :param who_to_connect: Wi-Fi client device
    :type who_to_connect: WLAN
    :param cpe: the CPE to connect to
    :type cpe: CPE
    """
    wifi = cpe.sw.wifi
    ssid, bssid, passphrase = wifi.enable_wifi(
        who_to_connect.network,
        who_to_connect.band,
    )
    # Connect appropriate client to the network
    who_to_connect.wifi_client_connect(
        ssid_name=ssid,
        password=passphrase,
        bssid=bssid,
        security_mode=who_to_connect.authentication,
    )


def list_wifi_ssid(device: WLAN) -> list[str]:
    """Return the list of Wi-Fi SSIDs.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Return the list of Wi-Fi SSIDs.

    :param device: WLAN device instance
    :type device: WLAN
    :return: list of Wi-Fi SSIDs
    :rtype: list[str]
    """
    return device.list_wifi_ssids()


def scan_ssid_name(device: WLAN, cpe: CPE) -> bool:
    """Scan for the particular SSID based on the network type and band.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Scan for the particular SSID based on the network type and band.

    :param device: WLAN device instance
    :type device: WLAN
    :param cpe: the CPE to connect to
    :type cpe: CPE
    :return: true if the SSID is available, false otherwise
    :rtype: bool
    """
    ssid_name = get_ssid(device.network, device.band, cpe=cpe)
    return wifi_check_ssid(device, ssid_name)


def wifi_check_ssid(device: WLAN, ssid_name: str) -> bool:
    """Check the SSID provided is present in the scan list.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Check the SSID provided is present in the scan list.

    :param device: WLAN device instance
    :type device: WLAN
    :param ssid_name: SSID name to be verified
    :type ssid_name: str
    :return: true if the ssid_name is available, false otherwise
    :rtype: bool
    """
    return ssid_name in list_wifi_ssid(device)


def is_wifi_connected(device: WLAN) -> bool:
    """Get the state of the interface.

    :param device: device instance
    :type device: WLAN
    :return: True if connected
    :rtype: bool
    """
    return device.is_wlan_connected()


@contextmanager
def enable_and_disable_monitor_mode(device: WLAN) -> Generator[None, Any, None]:
    """Enable and disbale monitor mode.

    :param device: device instance
    :type device: WLAN
    :yield: in between enabling and disabling monitor mode
    :rtype: Generator[None, Any, None]
    """
    try:
        device.enable_monitor_mode()
        yield
    finally:
        device.disable_monitor_mode()
