"""Boardfarm WLAN device template."""

# pylint: disable=duplicate-code

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Generator
    from ipaddress import IPv4Address, IPv4Network

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
        password: str | None = None,
        security_mode: str | None = None,
        bssid: str | None = None,
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
    def nmap(  # pylint: disable=too-many-arguments  # noqa: PLR0913
        self,
        ipaddr: str,
        ip_type: str,
        port: str | int | None = None,
        protocol: str | None = None,
        max_retries: int | None = None,
        min_rate: int | None = None,
        opts: str | None = None,
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
        self,
        fname: str,
        interface: str = "any",
        additional_args: str | None = None,
    ) -> Generator[str, None, None]:
        """Capture packets from specified interface.

        Packet capture using tcpdump utility at a specified interface.

        :param fname: name of the file where packet captures will be stored
        :param interface: name of the interface, defaults to "any"
        :param additional_args: argument arguments to tcpdump executable
        :yield: process id of tcpdump process
        """
        raise NotImplementedError

    @abstractmethod
    def enable_ipv6(self) -> None:
        """Enable ipv6 on the connected client interface."""
        raise NotImplementedError

    @abstractmethod
    def disable_ipv6(self) -> None:
        """Disable ipv6 on the connected client interface."""
        raise NotImplementedError

    @abstractmethod
    def get_interface_macaddr(self, interface: str) -> str:
        """Get the interface MAC address.

        :param interface: interface name
        :type interface: str
        :return: mac address of the interface
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_mask(self, interface: str) -> str:
        """Get the subnet mask of the interface.

        :param interface: name of the interface
        :type interface: str
        :return: subnet mask of interface
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_mtu_size(self, interface: str) -> int:
        """Get the MTU size of the interface in bytes.

        :param interface: name of the interface
        :type interface: str
        :return: size of the MTU in bytes
        :rtype: int
        """
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        """
        raise NotImplementedError

    @abstractmethod
    def perform_scp(
        self,
        source: str,
        destination: str,
        action: Literal["download", "upload"] = "download",
    ) -> None:
        """Perform SCP from linux device.

        :param source: source file path
        :type source: str
        :param destination: destination file path
        :type destination: str
        :param action: scp action(download/upload), defaults to "download"
        :type action: Literal["download", "upload"], optional
        """
        raise NotImplementedError

    @abstractmethod
    def start_traffic_receiver(
        self,
        traffic_port: int,
        bind_to_ip: str | None = None,
        ip_version: int | None = None,
    ) -> int | bool:
        """Start the server on a linux device to generate traffic using iperf3.

        :param traffic_port: server port to listen on
        :type traffic_port: int
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to None
        :type bind_to_ip: str, optional
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int, optional
        :return: the process id(pid) or False if pid could not be generated
        :rtype: Union[int, bool]
        """
        raise NotImplementedError

    @abstractmethod
    def start_traffic_sender(  # pylint: disable=too-many-arguments  # noqa: PLR0913
        self,
        host: str,
        traffic_port: int,
        bandwidth: int | None = None,
        bind_to_ip: str | None = None,
        direction: str | None = None,
        ip_version: int | None = None,
        udp_protocol: bool = False,
        time: int = 10,
    ) -> int | bool:
        """Start traffic on a linux client using iperf3.

        :param host: a host to run in client mode
        :type host: str
        :param traffic_port: server port to connect to
        :type traffic_port: int
        :param bandwidth: bandwidth(mbps) at which the traffic
            has to be generated, defaults to None
        :type bandwidth: Optional[int], optional
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to None
        :type bind_to_ip: Optional[str], optional
        :param direction: `--reverse` to run in reverse mode
            (server sends, client receives) or `--bidir` to run in
            bidirectional mode, defaults to None
        :type direction: Optional[str], optional
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int, optional
        :param udp_protocol: use UDP rather than TCP, defaults to False
        :type udp_protocol: bool, optional
        :param time: time in seconds to transmit for, defaults to 10
        :type time: int, optional
        :return: the process id(pid) or False if pid could not be generated
        :rtype: Union[int, bool]
        """
        raise NotImplementedError
