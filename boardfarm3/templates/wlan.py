"""Boardfarm WLAN device template."""

from abc import ABC, abstractmethod
from ipaddress import IPv4Address, IPv4Network
from typing import Optional


class WLAN(ABC):  # pylint: disable=too-many-public-methods
    """Boardfarm WLAN device template."""

    @property
    @abstractmethod
    def band(self) -> str:
        """Wifi band supported by the wlan device.

        :return: type of band i.e. 2.4, 5, dual
        :rtype: str
        """
        raise NotImplementedError

    @property
    def network(self) -> str:
        """Wifi network to which wlan device should connect.

        :return: type of network i.e. private, guest, community
        :rtype: str
        """
        raise NotImplementedError

    @property
    def authentication(self) -> str:
        """Wifi authentication through which wlan device should connect.

        :return: WPA-PSK, WPA2, etc
        :rtype: str
        """
        raise NotImplementedError

    @property
    def protocol(self) -> str:
        """Wifi protocol using which wlan device should connect.

        :return: 802.11ac, 802.11, etc
        :rtype: str
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def http_proxy(self) -> str:
        """SOCKS5 dante proxy address.

        :return: http://{proxy_ip}:{proxy_port}/
        :rtype: str
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT.

        :return: interface
        :rtype: str
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def lan_network(self) -> IPv4Network:
        """IPv4 WLAN Network.

        :return: IPv4 address network
        :rtype: IPv4Network
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def lan_gateway(self) -> IPv4Address:
        """WLAN gateway address.

        :return: Ipv4 wlan gateway address
        :rtype: IPv4Address
        """
        raise NotImplementedError

    @abstractmethod
    def reset_wifi_iface(self) -> None:
        """Disable and enable wifi interface.

        i.e., set the interface link to "down" and then to "up"
        This calls the disable wifi and enable wifi methods
        """
        raise NotImplementedError

    @abstractmethod
    def disable_wifi(self) -> None:
        """Disabling the wifi interface.

        Set the interface link to "down"
        """
        raise NotImplementedError

    @abstractmethod
    def enable_wifi(self) -> None:
        """Enable the wifi interface.

        Set the interface link to "up"
        """
        raise NotImplementedError

    @abstractmethod
    def dhcp_release_wlan_iface(self) -> None:
        """DHCP release the wifi interface."""
        raise NotImplementedError

    @abstractmethod
    def dhcp_renew_wlan_iface(self) -> bool:
        """DHCP renew of the wifi interface.

        :return: True if renew is success else False
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def set_wlan_scan_channel(self, channel: str) -> None:
        """Change wifi client scan channel.

        :param channel: wifi channel
        :type channel: str
        """
        raise NotImplementedError

    @abstractmethod
    def iwlist_supported_channels(self, wifi_band: str) -> list[str]:
        """List of wifi client support channels.

        :param wifi_mode: wifi frequency ['2' or '5']
        :type wifi_mode: str
        :return: list of channel in wifi mode
        :rtype: list[str]
        """
        raise NotImplementedError

    @abstractmethod
    def list_wifi_ssids(self) -> list[str]:
        """Scan for available WiFi SSIDs.

        :raises CodeError: WLAN card was blocked due to some process.
        :return: List of Wi-FI SSIDs
        :rtype: list[str]
        """
        raise NotImplementedError

    @abstractmethod
    def is_wifi_ssid_listed(self, ssid_name: str) -> bool:
        """Check the SSID provided is present in the scan list.

        :param ssid_name: SSID name to be verified
        :type ssid_name: str
        :return: True if given WiFi SSID is listed, False otherwise
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def wifi_client_connect(
        self,
        ssid_name: str,
        password: Optional[str] = None,
        security_mode: Optional[str] = None,
        bssid: Optional[str] = None,
    ) -> None:
        """Scan for SSID and verify wifi connectivity.

        :param ssid_name: SSID name
        :type ssid_name: str
        :param password: wifi password, defaults to None
        :type password: str, optional
        :param security_mode: Security mode for the wifi, defaults to None
        :type security_mode: str, optional
        :param bssid: BSSID of the desired network.
            Used to differentialte between 2.4/5 GHz networks with same SSID
        :type bssid: str, optional
        """
        raise NotImplementedError

    @abstractmethod
    def change_wifi_region(self, country: str) -> None:
        """Change the region of the wifi.

        :param country: region to be set
        :type country: str
        """
        raise NotImplementedError

    @abstractmethod
    def is_wlan_connected(self) -> bool:
        """Verify wifi is in the connected state.

        :return: True if wlan is connected, False otherwise
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def wifi_disconnect(self) -> None:
        """Disconnect wifi connectivity."""
        raise NotImplementedError

    @abstractmethod
    def disconnect_wpa(self) -> None:
        """Disconnect the wpa supplicant initialisation."""
        raise NotImplementedError
