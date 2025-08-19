"""Provisioner device template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.custom_typing.dhcp import (
        DHCPServicePools,
        DHCPv4Options,
        DHCPv6Options,
    )
    from boardfarm3.lib.networking import IptablesFirewall


# pylint: disable=too-few-public-methods


class Provisioner(ABC, BoardfarmDevice):
    """Boardfarm base provisioner device template."""

    @abstractmethod
    def provision_cpe(
        self,
        cpe_mac: str,
        dhcpv4_options: dict[DHCPServicePools, DHCPv4Options],
        dhcpv6_options: dict[DHCPServicePools, DHCPv6Options],
    ) -> None:
        """Provision the CPE.

        Adds a DHCP Host reservation in the provisioner.

        The host reservation can further be configured to also provide
        custom DHCP option data, depending on the option requested as part
        of the ```dhcpv4_option``` and ```dhcpv6_options``` arguments.

        .. code-block:: python

            mac = "AA:BB:CC:DD:EE:AA"
            provisioner = device_manager.get_device_by_type(Provisioner)

            # Provision a CPE MAC with default DHCP options
            provisioner.provision_cpe(
                cpe_mac=mac,
                dhcpv4_options={},
                dhcpv6_options={},
            )

            # Provision a CPE MAC with custom DHCP options
            # Note: This is a partial configuration.
            # If only partial details are provided, device class
            # will fill the remaining option data with defaults
            dhcpv4_options = {
                "data": {"dns-server": "x.x.x.x"},
                "voice": {"ntp-server": "y.y.y.y"},
            }
            provisioner.provision_cpe(
                cpe_mac=mac, dhcpv4_options=dhcpv4_options, dhcpv6_options={}
            )

        :param cpe_mac: CPE mac address
        :type cpe_mac: str
        :param dhcpv4_options: DHCPv4 Options with ACS, NTP, DNS details
        :type dhcpv4_options: dict[DHCPServicePools, DHCPv4Options]
        :param dhcpv6_options: DHCPv6 Options with ACS, NTP, DNS details
        :type dhcpv6_options: dict[DHCPServicePools, DHCPv6Options]

        """
        raise NotImplementedError

    @property
    @abstractmethod
    def console(self) -> BoardfarmPexpect:
        """Returns Provisioner console.

        :return: console
        :rtype: BoardfarmPexpect
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def firewall(self) -> IptablesFirewall:
        """Returns Firewall utility instance.

        :return: firewall utility instance with console object
        :rtype: IptablesFirewall
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT."""
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
        :param additional_args: additional arguments for tshark command
        :param timeout: timeout for tshark command to be executed, defaults to 30
        :param rm_pcap: If True remove the packet capture file after reading it
        :return: return tshark read command console output
        :raises  FileNotFoundError: when file is not found
        :raises BoardfarmException: when invalid filters are added
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
    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
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
