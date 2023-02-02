"""Boardfarm WLAN device template."""

# pylint: disable=duplicate-code

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from ipaddress import IPv4Address, IPv4Network
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from boardfarm3.lib.multicast import Multicast


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
    @abstractmethod
    def network(self) -> str:
        """Wifi network to which wlan device should connect.

        :return: type of network i.e. private, guest, community
        :rtype: str
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def authentication(self) -> str:
        """Wifi authentication through which wlan device should connect.

        :return: WPA-PSK, WPA2, etc
        :rtype: str
        """
        raise NotImplementedError

    @property
    @abstractmethod
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

    @property
    @abstractmethod
    def multicast(self) -> Multicast:
        """Return multicast component instance.

        :return: multicast component instance
        :rtype: Multicast
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

        :param wifi_band: wifi frequency ['2.4' or '5']
        :type wifi_band: str
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

    @abstractmethod
    def get_interface_ipv4addr(self, interface: str) -> str:
        """Return ipv4 address of the interface.

        :param interface: interface name
        :type interface: str
        :raises BoardfarmException: in case IPv4 is not found
        :return: IPv4 of the interface
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv6addr(self, interface: str) -> str:
        """Return ipv4 address of the interface.

        :param interface: interface name
        :type interface: str
        :raises BoardfarmException: in case IPv6 is not found
        :return: IPv6 of the interface
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def nmap(  # pylint: disable=too-many-arguments
        self,
        ipaddr: str,
        ip_type: str,
        port: Optional[Union[str, int]] = None,
        protocol: Optional[str] = None,
        max_retries: Optional[int] = None,
        min_rate: Optional[int] = None,
        opts: str = None,
    ) -> dict:
        """Perform nmap operation on linux device.

        :param ipaddr: ip address on which nmap is performed
        :type ipaddr: str
        :param ip_type: type of ip eg: ipv4/ipv6
        :type ip_type: str
        :param port: destination port on ip, defaults to None
        :type port: Optional[Union[str, int]], optional
        :param protocol: specific protocol to follow eg: tcp(-sT)/udp(-sU),
            defaults to None
        :type protocol: Optional[str], optional
        :param max_retries: number of port scan probe retransmissions, defaults to None
        :type max_retries: Optional[int], optional
        :param min_rate: Send packets no slower than per second, defaults to None
        :type min_rate: Optional[int], optional
        :param opts: other options for a nmap command, defaults to None
        :type opts: str, optional
        :raises BoardfarmException: Raises exception if ip type is invalid
        :return: response of nmap command in xml/dict format
        :rtype: dict
        """
        raise NotImplementedError

    @contextmanager
    @abstractmethod
    def tcpdump_capture(
        self, fname: str, interface: str = "any", additional_args: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Capture packets from specified interface.

        Packet capture using tcpdump utility at a specified interface.

        :param fname: name of the file where packet captures will be stored
        :param interface: name of the interface, defaults to "any"
        :param additional_args: argument arguments to tcpdump executable
        :yield: process id of tcpdump process
        """
        raise NotImplementedError
