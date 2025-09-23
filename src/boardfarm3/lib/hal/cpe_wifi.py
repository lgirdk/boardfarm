"""CPE WiFi HAL class."""

from __future__ import annotations

from abc import ABC, abstractmethod


class WiFiHal(ABC):
    """Contain CPE Wi-Fi software methods."""

    @property
    @abstractmethod
    def wlan_ifaces(self) -> dict[str, dict[str, str]]:
        """Get all the wlan interfaces on board.

        :return: interfaces e.g. private/guest/community
        :rtype: dict[str, dict[str, str]]
        """
        raise NotImplementedError

    @abstractmethod
    def get_ssid(self, network: str, band: str) -> str | None:
        """Get the wifi ssid for the wlan client with specific network and band.

        :param network: network type(private/guest/community)
        :type network: str
        :param band: wifi band(5/2.4 GHz)
        :type band: str
        :return: SSID of the WiFi for a given network type and band
        :rtype: Optional[str]
        """
        raise NotImplementedError

    @abstractmethod
    def get_bssid(self, network: str, band: str) -> str | None:
        """Get the wifi Basic Service Set Identifier.

        :param network: network type(private/guest/community)
        :type network: str
        :param band: wifi band(5/2.4 GHz)
        :type band: str
        :return: MAC physical address of the access point
        :rtype: Optional[str]
        """
        raise NotImplementedError

    @abstractmethod
    def get_passphrase(self, iface: str) -> str:
        """Get the passphrase for a network on an interface.

        :param iface: name of the interface
        :type iface: str
        :return: encrypted password for a network
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def is_wifi_enabled(self, network_type: str, band: str) -> bool:
        """Check if specific wifi is enabled.

        :param network_type: network type(private/guest/community)
        :type network_type: str
        :param band: wifi band(5/2.4 GHz)
        :type band: str
        :return: True if enabled, False otherwise
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def enable_wifi(self, network: str, band: str) -> tuple[str, str, str]:
        """Use Wifi Hal API to enable the wifi if not already enabled.

        :param network: network type(private/guest/community)
        :type network: str
        :param band: wifi band(5/2.4 GHz)
        :type band: str
        :return: tuple of ssid,bssid,passphrase
        :rtype: tuple[str, str, str]
        """
        raise NotImplementedError
