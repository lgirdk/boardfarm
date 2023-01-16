"""Boardfarm WAN device module."""

import logging
import re
from argparse import Namespace
from ipaddress import IPv4Interface, IPv6Interface
from typing import Any

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import ContingencyCheckError
from boardfarm3.lib.networking import NSLookup
from boardfarm3.lib.regexlib import AllValidIpv6AddressesRegex
from boardfarm3.lib.utils import get_value_from_dict
from boardfarm3.templates.wan import WAN

_LOGGER = logging.getLogger(__name__)


class LinuxWAN(LinuxDevice, WAN):
    """Boardfarm WAN device."""

    _tftpboot_dir = "/tftpboot"

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize LinuxWAN device.

        :param config: device configuration
        :type config: dict
        :param cmdline_args: command line arguments
        :type cmdline_args: Namespace
        """
        self._static_route = ""
        self._wan_dhcp = False
        self._wan_no_eth0 = False
        self._wan_dhcp_server = False
        self._wan_dhcpv6 = False
        super().__init__(config, cmdline_args)

    def _setup_wan(self) -> None:  # noqa: C901
        if "options" not in self._config:
            return
        self._console.execute_command(f"ifconfig {self.iface_dut} down")
        self._console.execute_command(f"ifconfig {self.iface_dut} up")
        options = [x.strip() for x in self._config["options"].split(",")]
        for opt in options:
            if opt.startswith("wan-static-route:"):
                self._static_route = opt.replace("wan-static-route:", "").replace(
                    "-", " via "
                )
            elif opt == "wan-dhcp-client":
                self._wan_dhcp = True
            elif opt == "wan-no-eth0":
                self._wan_no_eth0 = True
            elif opt == "wan-no-dhcp-server":
                self._wan_dhcp_server = False
            elif opt == "wan-dhcp-client-v6":
                self._wan_dhcpv6 = True
            elif opt.startswith("wan-static-ipv6:"):
                ipv6_address = opt.replace("wan-static-ipv6:", "")
                ipv6_interface = IPv6Interface(ipv6_address)
                # we are bypassing this for now
                # (see http://patchwork.ozlabs.org/patch/117949/)
                self._console.execute_command(
                    f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0"
                )
                self._console.execute_command(
                    f"ip -6 addr del {ipv6_interface} dev {self.iface_dut}"
                )
                self._console.execute_command(
                    f"ip -6 addr add {ipv6_interface} dev {self.iface_dut}"
                )
            elif opt.startswith("wan-static-ip:"):
                value = str(opt.replace("wan-static-ip:", ""))
                ipv4_interface = IPv4Interface(value)
                self._console.execute_command(
                    f"ip -4 addr del {ipv4_interface} dev {self.iface_dut}"
                )
                self._console.execute_command(
                    f"ip -4 addr add {ipv4_interface} dev {self.iface_dut}"
                )
        if self._static_route:
            for route in self._static_route.split(";"):
                self._console.execute_command(f"ip route del {route.split('via')[0]}")
                self._console.execute_command(f"ip route add {route}")

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot WAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        if self._cmdline_args.skip_boot:
            return
        self._setup_wan()  # to be revisited when docker factory is implemented

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown WAN device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    @hookimpl
    def contingency_check(self, env_req: dict[str, Any]) -> None:
        """Make sure the WAN is working fine before use.

        :param env_req: test env request
        :type env_req: dict[str, Any]
        """
        if self._cmdline_args.skip_contingency_checks:
            return
        _LOGGER.info("Contingency check %s(%s)", self.device_name, self.device_type)
        self.get_eth_interface_ipv4_address()
        self.get_eth_interface_ipv6_address()
        # Perform DNS service check
        if acs_server_config := get_value_from_dict("ACS_SERVER", env_req):
            self._validate_dns_env_request(acs_server_config)

    def _validate_dns_env_request(
        self, acs_server_config: dict[str, dict[str, str]]
    ) -> None:
        output = NSLookup(self._console).nslookup("acs_server.boardfarm.com")
        ping_status = {
            "ipv4": {"reachable": 0, "unreachable": 0},
            "ipv6": {"reachable": 0, "unreachable": 0},
        }
        for ip_address in output.get("domain_ip_addr", []):
            ip_version = (
                "ipv6" if re.match(AllValidIpv6AddressesRegex, ip_address) else "ipv4"
            )
            if self.ping(ip_address, ping_count=2):
                ping_status[ip_version]["reachable"] += 1
            else:
                ping_status[ip_version]["unreachable"] += 1
        for ip_version, item in ping_status.items():
            if ip_version not in acs_server_config:
                continue
            for status, value in item.items():
                if status not in acs_server_config[ip_version]:
                    continue
                if acs_server_config[ip_version][status] != value:
                    raise ContingencyCheckError(
                        f"DNS check failed for {ip_version} {status} servers -"
                        f" requested: {acs_server_config[ip_version][status]},"
                        f" actual: {value}"
                    )

    @property
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT.

        :returns: the DUT interface name
        :rtype: str
        """
        return self.eth_interface

    def copy_local_file_to_tftpboot(self, local_file_path: str) -> None:
        """SCP local file to tftpboot directory.

        :param local_file_path: local file path
        :type local_file_path: str
        """
        self.scp_local_file_to_device(local_file_path, self._tftpboot_dir)

    def download_image_to_tftpboot(self, image_uri: str) -> str:
        """Download image from URL to tftpboot directory.

        :param image_uri: image file URI
        :type image_uri: str
        :returns: name of the image in tftpboot
        :rtype: str
        """
        return self.download_file_from_uri(image_uri, self._tftpboot_dir)

    def execute_snmp_command(self, snmp_command: str) -> str:
        """Execute snmp command.

        :param snmp_command: snmp command
        :type snmp_command: str
        :returns: snmp command output
        :rtype: str
        :raises ValueError: when snmp command is invalid
        """
        # Only allowing snmp commands to be executed from wan
        # only wan has snmp utils installed on it.
        if not snmp_command.startswith("snmp"):
            raise ValueError(f"{snmp_command!r} is not a SNMP command")
        return self._console.execute_command(snmp_command)
