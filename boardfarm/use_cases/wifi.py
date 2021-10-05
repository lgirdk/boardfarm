"""Wifi use cases library.
All APIs are independent of board under test.
"""
from dataclasses import dataclass
from typing import Optional

from boardfarm.devices.base_devices.wifi_template import WIFITemplate
from boardfarm.lib.DeviceManager import get_device_by_name
from boardfarm.lib.wifi_lib import wifi_mgr


@dataclass
class WifiClient:
    band: str
    __obj: WIFITemplate
    network_type: str
    authentication: Optional[str] = "WPA-PSK"
    protocol: Optional[str] = "802.11n"

    def _obj(self):
        return self.__obj


def get_wifi_client(band: float, network_type: str) -> WifiClient:
    """Get the wifi client.
    :param band: band of the client
    :type band: float
    :param network_type: network type of the client Eg: private,guest,community
    :type network_type: string
    :return: Wificlient
    :rtype: object
    """
    dev = wifi_mgr.filter(network_type, band=str(band))[0]
    return WifiClient(band, dev, network_type=network_type)


def _get_ssid(network: str, band: float, mode: str = "console") -> str:

    """Get the wifi ssid.
    :param network_type: network type of the client Eg: private,guest,community
    :type network_type: string
    :param band: band of the client
    :type band: float
    :param mode: mode to get the ssid Eg. snmp,acs,dmcli
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
    :param mode: mode to get the bssid Eg. console,snmp,acs,dmcli
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
    """Get the wifi ssid.
    :param network_type: network type of the client Eg: private,guest,community
    :type network_type: string
    :return: passphrase
    :rtype: string
    """
    board_wifi = get_device_by_name("board").wifi
    return getattr(board_wifi.console, f"{network}_passphrase")()


def is_client_connected(who_is_connected: WifiClient) -> bool:
    """To check if the client is connected.
    :param who_is_connected: client to connect
    :type who_is_connected: string
    :return: true/False
    :rtype: bool
    """
    return who_is_connected._obj().is_wlan_connected()


def connect_wifi_client(
    who_to_connect: WifiClient,
    ssid: str = None,
    password: str = None,
    bssid: str = None,
) -> None:
    """connect to the Wifi client.
    :param who_to_connect: client to connect
    :type who_to_connect: string
    :param ssid: ssid of the client to connect
    :type ssid: string
    :param password: password of the client to connect
    :type password: string
    :param bssid: bssid of the client to connect
    :type bssid: string
    """
    if not ssid:
        ssid = _get_ssid(who_to_connect.network_type, who_to_connect.band)
    if not bssid:
        bssid = _get_bssid(who_to_connect.network_type, who_to_connect.band)
    if not password:
        password = _get_passphrase(who_to_connect.network_type)
    who_to_connect._obj().wifi_client_connect(
        ssid_name=ssid,
        password=password,
        security_mode=who_to_connect.authentication,
        bssid=bssid,
    )


def disconnect_wifi_client(who_to_disconnect: WifiClient) -> None:
    """disconnect to the Wifi client.
    :param who_to_disconnect: client to disconnect
    :type who_to_disconnect: string
    """
    who_to_disconnect._obj().wifi_disconnect()
