"""Boardfarm WLAN device template."""

# pylint: disable=duplicate-code

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
    from ipaddress import IPv4Address, IPv4Network

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.multicast import Multicast, MulticastGroupRecord


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

    @property
    @abstractmethod
    def console(self) -> BoardfarmPexpect:
        """Returns WLAN console.

        :return: console
        :rtype: BoardfarmPexpect
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
    def start_ipv4_wlan_client(self) -> bool:
        """Restart ipv4 dhclient to obtain an IP.

        :return: True if renew is success else False
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def start_ipv6_wlan_client(self) -> None:
        """Restart ipv6 dhclient to obtain IP."""
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
        timeout: int = 30,
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
        :param timeout: pexpect timeout for the command in seconds, defaults to 30
        :type timeout: int
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
    ) -> Generator[str]:
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
    def scp_device_file_to_local(self, local_path: str, source_path: str) -> None:
        """Copy a local file from a server using SCP.

        :param local_path: local file path
        :param source_path: source path
        """
        raise NotImplementedError

    @abstractmethod
    def start_traffic_receiver(
        self,
        traffic_port: int,
        bind_to_ip: str | None = None,
        ip_version: int | None = None,
        udp_only: bool | None = None,
    ) -> tuple[int, str]:
        """Start the server on a linux device to generate traffic using iperf3.

        :param traffic_port: server port to listen on
        :type traffic_port: int
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to None
        :type bind_to_ip: str, optional
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int, optional
        :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
        :type udp_only: bool, optional
        :raises CodeError: raises if unable to start server
        :return: the process id(pid) and log file path
        :rtype: tuple[int, str]
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
        client_port: int | None = None,
        udp_only: bool | None = None,
    ) -> tuple[int, str]:
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
        :type udp_protocol: bool
        :param time: time in seconds to transmit for, defaults to 10
        :type time: int
        :param client_port: client port from where the traffic is getting started
        :type client_port: int | None
        :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
        :type udp_only: bool, optional
        :raises CodeError: raises if unable to start server
        :return: the process id(pid) and log file path
        :rtype: tuple[int, str]
        """
        raise NotImplementedError

    @abstractmethod
    def stop_traffic(self, pid: int | None = None) -> bool:
        """Stop the iPerf3 process for a specific PID or killall.

        :param pid: process ID for a iPerf3 service either for reciever or sender,
            defaults to None
        :type pid: int | None
        :return: True if process is stopped else False
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def get_iperf_logs(self, log_file: str) -> str:
        """Read the file output for traffic flow.

        :param log_file: iperf log file path
        :type log_file: str
        :return: traffic flow logs
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def set_link_state(self, interface: str, state: str) -> None:
        """Set link state.

        :param interface: name of the interface
        :type interface: str
        :param state: desired state up or down
        :type state: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_date(self) -> str | None:
        """Get the system date and time.

        .. code-block:: python

            # example output
            donderdag, mei 23, 2024 14:23:39


        :return: date
        :rtype: str | None
        """
        raise NotImplementedError

    @abstractmethod
    def set_date(self, opt: str, date_string: str) -> bool:
        """Set the device's date and time.

        :param date_string: value to be changed
        :type date_string: str
        :param opt: Option to set the date or time or day
        :type opt: str
        :return: True if set is successful
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def send_mldv2_report(
        self, mcast_group_record: MulticastGroupRecord, count: int
    ) -> None:
        """Send an MLDv2 report with desired multicast record.

        Multicast source and group must be IPv6 addresses.
        Multicast sources need to be non-multicast addresses and
        group address needs to be a multicast address.

        Implementation relies on a custom send_mld_report
        script based on scapy.

        :param mcast_group_record: MLDv2 multicast group record
        :type mcast_group_record: MulticastGroupRecord
        :param count: num of packets to send in 1s interval
        :type count: int
        :raises CodeError: if send_mld_report command fails
        """
        raise NotImplementedError

    @cached_property
    @abstractmethod
    def ipv4_addr(self) -> str:
        """Return the IPv4 address on IFACE facing DUT.

        :return: IPv4 address in string format.
        :rtype: str
        """
        raise NotImplementedError

    @cached_property
    @abstractmethod
    def ipv6_addr(self) -> str:
        """Return the IPv6 address on IFACE facing DUT.

        :return: IPv6 address in string format.
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def ping(  # noqa: PLR0913
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: str | None = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> bool | dict[str, Any]:
        """Ping remote host.

        Return True if ping has 0% loss
        or parsed output in JSON if json_output=True flag is provided.

        :param ping_ip: ping IP
        :type ping_ip: str
        :param ping_count: number of ping, defaults to 4
        :type ping_count: int
        :param ping_interface: ping via interface, defaults to None
        :type ping_interface: str
        :param options: extra ping options, defaults to ""
        :type options: str
        :param timeout: timeout, defaults to 50
        :type timeout: int
        :param json_output: return ping output in dictionary format, defaults to False
        :type json_output: bool
        :return: ping output
        :rtype: bool | dict[str, Any]
        """
        raise NotImplementedError

    @abstractmethod
    def release_dhcp(self, interface: str) -> None:
        """Release IPv4 of the specified interface.

        :param interface: interface name
        :type interface: str
        """
        raise NotImplementedError

    @abstractmethod
    def renew_dhcp(self, interface: str) -> None:
        """Renew IPv4 of the specified interface by restart of the IPv4 dhclient.

        :param interface: interface name
        :type interface: str
        """
        raise NotImplementedError

    @abstractmethod
    def release_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Release IPv6 of the specified interface.

        :param interface: interface name
        :type interface: str
        :param stateless: run command with -S or -6 options. -6 by default
        :type stateless: bool
        """
        raise NotImplementedError

    @abstractmethod
    def renew_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Renew IPv6 of the specified interface.

        :param interface: interface name
        :type interface: str
        :param stateless: run command with -S or -6 options. -6 by default
        :type stateless: bool
        """
        raise NotImplementedError

    @abstractmethod
    def enable_monitor_mode(self) -> None:
        """Enable monitor mode on WLAN interface.

        Set the type to monitor
        """
        raise NotImplementedError

    @abstractmethod
    def disable_monitor_mode(self) -> None:
        """Disable monitor mode on WLAN interface.

        Set the type to managed
        """
        raise NotImplementedError

    @abstractmethod
    def is_monitor_mode_enabled(self) -> bool:
        """Check if monitor mode is enabled on WLAN interface.

        :return: Status of monitor mode
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def tshark_read_pcap(
        self,
        fname: str,
        additional_args: str | None = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file.

        :param fname: name of the file in which captures are saved
        :type fname: str
        :param additional_args: additional arguments for tshark command
        :type additional_args: str
        :param timeout: time out for tshark command to be executed, defaults to 30
        :type timeout: int
        :param rm_pcap: If True remove the packet capture file after reading it
        :type rm_pcap: bool
        :return: return tshark read command console output
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_hostname(self) -> str:
        """Get the hostname of the device.

        :return: hostname of the device
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_process_id(self, process_name: str) -> list[str] | None:
        """Return the process id to the device.

        :param process_name: name of the process
        :type process_name: str
        :return: process id if the process exist, else None
        :rtype: list[str] | None
        """
        raise NotImplementedError

    @abstractmethod
    def kill_process(self, pid: int, signal: int) -> None:
        """Kill the running process based on the process id.

        :param pid: process id
        :type pid: int
        :type signal: signal number to terminate the process
        :type signal: int
        """
        raise NotImplementedError

    @abstractmethod
    def start_tcpdump(
        self,
        interface: str,
        port: str | None,
        output_file: str = "pkt_capture.pcap",
        filters: dict | None = None,
        additional_filters: str | None = "",
    ) -> str:
        """Start tcpdump capture on given interface.

        :param interface: inteface name where packets to be captured
        :type interface: str
        :param port: port number, can be a range of ports(eg: 443 or 433-443)
        :type port: str
        :param output_file: pcap file name, Defaults: pkt_capture.pcap
        :type output_file: str
        :param filters: filters as key value pair(eg: {"-v": "", "-c": "4"})
        :type filters: Optional[Dict]
        :param additional_filters: additional filters
        :type additional_filters: Optional[str]
        :raises ValueError: on failed to start tcpdump
        :return: console ouput and tcpdump process id
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def stop_tcpdump(self, process_id: str) -> None:
        """Stop tcpdump capture.

        :param process_id: tcpdump process id
        :type process_id: str
        """
        raise NotImplementedError
