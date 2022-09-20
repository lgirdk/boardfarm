"""Wifi use cases library.

All APIs are independent of board under test.
"""
from typing import Generator, List, Tuple

from boardfarm.devices.base_devices.wifi_template import WIFITemplate
from boardfarm.lib.DeviceManager import get_device_by_name
from boardfarm.lib.wifi_lib import wifi_mgr

wifi_resource_output = Tuple[List[WIFITemplate], List[WIFITemplate]]

wifi_resource_generator = Generator[wifi_resource_output, None, None]


def get_wifi_client(band: float, network_type: str) -> WIFITemplate:
    """Get the wifi client.

    :param band: band of the client
    :type band: float
    :param network_type: network type of the client Eg: private,guest,community
    :type network_type: string
    :return: Wifi client
    :rtype: WIFITemplate
    """
    dev = wifi_mgr.filter(network_type, band=band)[0]
    dev.band = band
    dev.network_type = network_type
    return dev


def _get_ssid(network: str, band: float, mode: str = "console") -> str:
    """Get the wifi ssid.

    :param network_type: network type of the client Eg: private,guest,community
    :type network_type: string
    :param band: band of the client
    :type band: float
    :param mode: mode to get the ssid Eg. snmp,acs,dmcli,console(default)
    :type mode: str
    :return: ssid
    :rtype: string
    """
    if mode == "console":
        board_wifi = get_device_by_name("board").wifi
        return getattr(board_wifi.console, f"{network}_ssid")(str(band))
    if mode == "snmp":
        # To be implemented
        raise Exception("Not implemented")


def _get_bssid(network: str, band: float, mode: str = "console") -> str:
    """Get the wifi bssid.

    :param network_type: network type of the client Eg: private,guest,community
    :type network_type: string
    :param band: band of the client
    :type band: float
    :param mode: mode to get the bssid Eg. console(default),snmp,acs,dmcli
    :type mode: str
    :return: bssid
    :rtype: string
    """
    if mode == "console":
        board_wifi = get_device_by_name("board").wifi
        return getattr(board_wifi.console, f"{network}_bssid")(str(band))
    if mode == "snmp":
        # To be implemented
        raise Exception("Not implemented")


def _get_passphrase(network: str) -> str:
    """Get the wifi passphrase.

    :param network_type: network type of the client Eg: private,guest,community
    :type network_type: string
    :return: passphrase
    :rtype: string
    """
    board_wifi = get_device_by_name("board").wifi
    return getattr(board_wifi.console, f"{network}_passphrase")()


def is_client_connected(who_is_connected: WIFITemplate) -> bool:
    """Check if the client is connected.

    :param who_is_connected: client to connect
    :type who_is_connected: WIFITemplate
    :return: True if client is connected on L2 and L3, False otherwise
    :rtype: bool
    """
    return who_is_connected.is_wlan_connected()


def connect_wifi_client(
    who_to_connect: WIFITemplate,
    ssid: str = None,
    password: str = None,
    bssid: str = None,
) -> None:
    """Connect client to Wifi.

    :param who_to_connect: client to connect
    :type who_to_connect: WIFITemplate
    :param ssid: ssid of the network to connect
    :type ssid: string
    :param password: password of the network to connect
    :type password: string
    :param bssid: bssid of the network to connect
    :type bssid: string
    """
    if not ssid:
        ssid = _get_ssid(who_to_connect.network_type, who_to_connect.band)
    if not bssid:
        bssid = _get_bssid(who_to_connect.network_type, who_to_connect.band)
    if not password:
        password = _get_passphrase(who_to_connect.network_type)
    who_to_connect.wifi_client_connect(
        ssid_name=ssid,
        password=password,
        security_mode=who_to_connect.authentication,
        bssid=bssid,
    )


def disconnect_wifi_client(who_to_disconnect: WIFITemplate) -> None:
    """Disconnect client from Wifi.

    :param who_to_disconnect: client to disconnect
    :type who_to_disconnect: WIFITemplate
    """
    who_to_disconnect.wifi_disconnect()
