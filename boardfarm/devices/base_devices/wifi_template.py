from abc import abstractmethod
from typing import List

from boardfarm.devices.linux import LinuxInterface
from boardfarm.lib.signature_checker import __MetaSignatureChecker


class WIFITemplate(LinuxInterface, metaclass=__MetaSignatureChecker):
    """WIFI server template class."""

    @abstractmethod
    def __init__(self, *args, **kwargs):
        """Initialize WIFI parameters.
        Config data dictionary will be unpacked and passed to init as kwargs.
        You can use kwargs in a following way:
            self.username = kwargs.get("username", "DEFAULT_USERNAME")
            self.password = kwargs.get("password", "DEFAULT_PASSWORD")
        """
        super().__init__(*args, **kwargs)

    @abstractmethod
    def reset_wifi_iface(self) -> None:
        """Disable and enable wifi interface.
        i.e., set the interface link to "down" and then to "up"
        This calls the disable wifi and enable wifi methods
        """

    @abstractmethod
    def disable_wifi(self) -> None:
        """Disabling the wifi interface.
        setting the interface link to "down"
        """

    @abstractmethod
    def enable_wifi(self) -> None:
        """Enable the wifi interface.
        setting the interface link to "down"
        """

    @abstractmethod
    def dhcp_release_wlan_iface(self) -> None:
        """DHCP release the wifi interface."""

    @abstractmethod
    def dhcp_renew_wlan_iface(self) -> None:
        """DHCP renew the wifi interface."""

    @abstractmethod
    def set_wlan_scan_channel(self, channel: str) -> None:
        """Change wifi client scan channel.
        :param channel: wifi channel
        :type channel: string"""

    @abstractmethod
    def iwlist_supported_channels(self, wifi_band: str) -> None:
        """list of wifi client support channel.
        :param wifi_mode: wifi frequency ['2' or '5']
        :type wifi_mode: string
        :return: list of channel in wifi mode
        :rtype: list
        """

    @abstractmethod
    def list_wifi_ssids(self) -> List[str]:
        """To scan for available WiFi SSIDs
        :raises CodeError: WLAN card was blocked due to some process.
        :return: List of Wi-FI SSIDs
        :rtype: List[str]
        """

    @abstractmethod
    def wifi_check_ssid(self, ssid_name: str) -> bool:
        """Check the SSID provided is present in the scan list.
        :param ssid_name: SSID name to be verified
        :type ssid_name: string
        :return: True or False
        :rtype: boolean
        """

    @abstractmethod
    def wifi_client_connect(
        self,
        ssid_name: str,
        password: str = None,
        security_mode: str = None,
        bssid: str = None,
    ) -> None:
        """Scan for SSID and verify wifi connectivity.
        :param ssid_name: SSID name
        :type ssid_name: string
        :param password: wifi password, defaults to None
        :type password: string, optional
        :param security_mode: Security mode for the wifi, defaults to None
        :param bssid: BSSID of the desired network. Used to differentialte between 2.4\5 GHz networks with same SSID
        :type bssid: string, optional
        :type security_mode: string, optional
        :raise assertion: If SSID value check in WLAN container fails,
                          If connection establishment in WIFI fails
        """

    @abstractmethod
    def is_wlan_connected(self) -> bool:
        """Verify wifi is in the connected state.
        :return: True or False
        :rtype: boolean
        """

    @abstractmethod
    def wifi_disconnect(self) -> None:
        """Disconnect wifi connectivity."""
