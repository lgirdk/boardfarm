"""Boardfarm LAN device module."""

import binascii
import logging
import re
from argparse import Namespace
from ipaddress import AddressValueError, IPv4Address
from typing import Dict, Optional, Union

import pexpect
from termcolor import colored

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.templates.lan import LAN

_LOGGER = logging.getLogger(__name__)


class LinuxLAN(LinuxDevice, LAN):
    """Boardfarm LAN device."""

    def __init__(self, config: Dict, cmdline_args: Namespace) -> None:
        """Initialize linux LAN device.

        :param config: device configuration
        :type config: Dict
        :param cmdline_args: command line arguments
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)
        self.ipv4_client_started: bool = False

    @property
    def http_proxy(self) -> str:
        """SOCKS5 dante proxy address, e.g http://{proxy_ip}:{proxy_port}/."""
        return self._config.get("http_proxy")

    @property
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT."""
        return self.eth_interface

    @hookimpl
    def boardfarm_attached_device_boot(self) -> None:
        """Boardfarm hook implementation to boot LAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown LAN device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    @property
    def lan_gateway(self) -> str:
        """LAN gateway address."""
        # TODO: resolve lan gateway address dynamically
        return "192.168.178.1"

    def get_default_gateway(self) -> IPv4Address:
        """Get default gateway from ip route output."""
        self._console.sendline("ip route list 0/0 | awk '{print $3}'")
        self._console.expect(self._shell_prompt)
        try:
            return IPv4Address(str(self._console.before.strip()))
        except AddressValueError:
            # Should we just raise an exception instead?
            _LOGGER.warning(
                "Unable to resolve lan client gateway IP. "
                "Using default Ziggo address now. (192.168.178.1)"
            )
            return IPv4Address("192.168.178.1")

    def __kill_dhclient(self, ipv4: bool = True) -> None:
        dhclient_str = f"dhclient {'-4' if ipv4 else '-6'}"

        if ipv4:
            self.release_dhcp(self.iface_dut)
        else:
            self.release_ipv6(self.iface_dut)

        self._console.sendline("ps aux")
        if self._console.expect([dhclient_str] + self._shell_prompt) == 0:
            _LOGGER.warning(
                "WARN: dhclient still running, something started rogue client!"
            )
            self._console.sendline(
                f"pkill --signal 9 -f {dhclient_str}.*{self.iface_dut}"
            )
            self._console.expect(self._shell_prompt)

        self._console.sendline(f"kill $(</run/dhclient{'' if ipv4 else 6}.pid)")
        self._console.expect(self._shell_prompt)

    def start_ipv4_lan_client(
        self, wan_gw: Optional[Union[str, IPv4Address]] = None, prep_iface: bool = False
    ) -> str:
        """Restart ipv4 dhclient to obtain an IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :param prep_iface: restart interface before dhclient request
        :return: IPv4 after renewal
        :raises pexpect.TimeoutException: in case of failure.
        """
        # pylint: disable=too-many-statements
        ipv4 = None

        self.check_dut_iface()

        if prep_iface:
            self._console.sendline(
                f"ip link set down {self.iface_dut} && ip link set up {self.iface_dut}"
            )
            self._console.expect(self._shell_prompt)

        self.__kill_dhclient()

        self._console.sendline(f"\nifconfig {self.iface_dut} 0.0.0.0")
        self._console.expect(self._shell_prompt)
        self._console.sendline("rm /var/lib/dhcp/dhclient.leases")
        self._console.expect(self._shell_prompt)
        self._console.sendline(
            "sed -e 's/mv -f $new_resolv_conf $resolv_conf/cat $new_resolv_conf "
            "> $resolv_conf/g' -i /sbin/dhclient-script"
        )
        self._console.expect(self._shell_prompt)
        if self.mgmt_dns is not None:
            self._console.sendline(
                f"sed '/append domain-name-servers {self.mgmt_dns}/d' "
                "-i /etc/dhcp/dhclient.conf"
            )
            self._console.expect(self._shell_prompt)
            self._console.sendline(
                f'echo "append domain-name-servers {self.mgmt_dns};" >> '
                "/etc/dhcp/dhclient.conf"
            )
            self._console.expect(self._shell_prompt)

        self.configure_dhclient_option60(enable=True)
        self.configure_dhclient_option61(enable=True)

        for _ in range(5):
            try:
                self.renew_dhcp(self.iface_dut)
                self.get_interface_ipv4addr(self.iface_dut)
                break
            except Exception:  # pylint: disable=broad-except
                self._console.sendcontrol("c")
                self._console.expect(self._shell_prompt)

        self._console.sendline("cat /etc/resolv.conf")
        self._console.expect(self._shell_prompt)
        self._console.sendline(f"ip addr show dev {self.iface_dut}")
        self._console.expect(self._shell_prompt)
        self._console.sendline("ip route")
        # we should verify this so other way, because they could be the same subnets
        # in theory
        i = self._console.expect(
            [
                f"default via {self.lan_gateway} dev {self.iface_dut}",
                pexpect.TIMEOUT,
            ],
            timeout=5,
        )
        if i == 1:
            # update gw
            self._console.sendline("ip route list 0/0 | awk '{print $3}'")
            self._console.expect_exact("ip route list 0/0 | awk '{print $3}'")
            self._console.expect(self._shell_prompt)

            ip_addr = self.get_interface_ipv4addr(self.iface_dut)
            self._console.sendline(f"ip route | grep {ip_addr} | awk '{{print $1}}'")
            self._console.expect_exact(
                f"ip route | grep {ip_addr} | awk '{{print $1}}'"
            )
            self._console.expect(self._shell_prompt)

        if wan_gw is not None and hasattr(self, "lan_fixed_route_to_wan"):
            self._console.sendline(f"ip route add {wan_gw} via {self.lan_gateway}")
            self._console.expect(self._shell_prompt)
        ipv4 = self.get_interface_ipv4addr(self.iface_dut)

        if ipv4:
            self.ipv4_client_started = True

        return ipv4

    def start_ipv6_lan_client(
        self, wan_gw: Optional[Union[str, IPv4Address]] = None, prep_iface: bool = False
    ) -> str:
        """Restart ipv6 dhclient to obtain IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :param prep_iface: restart interface before dhclient request
        :return: IPv6 after renewal
        :raises pexpect.TimeoutException: in case of failure
        """
        raise NotImplementedError()

    def check_dut_iface(self) -> str:
        """Check that the dut iface exists and has a carrier."""
        output = self._console.check_output(f"ip link show {self.iface_dut}")
        if (
            self.iface_dut not in output
            or f'Device "{self.iface_dut}" does not exist' in output
        ):
            output = self._console.check_output("ip link")
            msg = colored(
                f"{self.device_name}: {self.iface_dut} NOT found\n{output}",
                color="red",
                attrs=["bold"],
            )
            _LOGGER.error(msg)
            raise Exception(msg)
        if "NO-CARRIER" in output:
            msg = colored(
                f"{self.device_name}: {self.iface_dut} CARRIER DOWN\n{output}",
                color="red",
                attrs=["bold"],
            )
            _LOGGER.error(msg)
        return output

    def configure_dhclient_option60(self, enable: bool) -> None:
        """Configure dhcp server option 60 in dhclient.conf.

        :param enable: add option 60 if True else remove
        """
        if enable:
            out = self._console.check_output(
                "egrep 'vendor-class-identifier' /etc/dhcp/dhclient.conf"
            )
            if not re.search("vendor-class-identifier", out):
                self._console.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
                self._console.sendline('send vendor-class-identifier "BFClient";')
                self._console.sendline("EOF")
                self._console.expect(self._shell_prompt)
        else:
            self._console.sendline(
                "sed -i '/vendor-class-identifier/d' /etc/dhcp/dhclient.conf"
            )
            self._console.expect(self._shell_prompt)

    def configure_dhclient_option61(self, enable: bool) -> None:
        """Configure dhcp server option 61 in dhclient.conf.

        :param enable: add option 61 if True else remove
        """
        if enable:
            mac = self.get_interface_macaddr(self.iface_dut)
            cmd = (
                r"sed -i -e 's/^#\{0,\}send dhcp-client-identifier.*/send "
                rf"dhcp-client-identifier {mac};/' /etc/dhcp/dhclient.conf"
            )
        else:
            cmd = (
                "sed -i -e 's/^send dhcp-client-identifier"
                "/#send dhcp-client-identifier/' /etc/dhcp/dhclient.conf"
            )
        self._console.check_output(cmd)
        self._console.check_output(
            "cat /etc/dhcp/dhclient.conf |grep dhcp-client-identifier"
        )

    def configure_dhclient_option125(self, enable: bool) -> None:
        """Configure dhcp server option 125 in dhclient.conf.

        :param enable: add option 125 if True else remove
        """
        if not enable:
            self._console.sendline(
                "sed -i -e 's|request option-125,|request |' /etc/dhcp/dhclient.conf"
            )
            self._console.expect(self._shell_prompt)
            self._console.sendline("sed -i '/option-125/d' /etc/dhcp/dhclient.conf")
            self._console.expect(self._shell_prompt)
        else:
            out = self._console.check_output(
                "egrep 'request option-125' /etc/dhcp/dhclient.conf"
            )
            if not re.search("request option-125,", out):
                self._console.sendline(
                    "sed -i -e 's|request |\\n"
                    "option option-125 code 125 = string;\\n\\n"
                    "request option-125, |' /etc/dhcp/dhclient.conf"
                )
                self._console.expect(self._shell_prompt)
                # details of Text for HexaDecimal value as
                # Enterprise code (3561) 00:00:0D:E9 length  (22)16
                # code 01  length 06  (BFVER0) 42:46:56:45:52:30
                # code 03  length 06  (BFCLAN)  42:46:43:4c:41:4e
                mac = self.get_interface_macaddr(self.iface_dut)
                value = "VAAU" + "".join(mac.split(":")[0:4]).upper()
                encoded_name = str.encode(value)
                hex_name = iter(binascii.hexlify(encoded_name).decode("utf-8"))
                code_02 = ":".join([f"{j}{k}" for j, k in zip(hex_name, hex_name)])
                len_02 = hex(len(value)).replace("0x", "").zfill(2)
                total_len = hex(18 + len(value)).replace("0x", "").zfill(2)
                option_125 = (
                    f"00:00:0D:E9:{total_len}:01:06:44:38:42:36:42:37:02:"
                    f"{len_02}:{code_02}:03:06:42:46:43:4c:41:4e"
                )
                self._console.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
                self._console.sendline(f"send option-125 = {option_125};")
                self._console.sendline("")
                self._console.sendline("EOF")
                self._console.expect(self._shell_prompt)

    def configure_dhcpv6_option17(self, enable: bool) -> None:
        """Configure LAN identity DHCPv6 option 17.

        :param enable: Add dhcpv6 option 17 if True else remove
        """
        if not enable:
            self._console.sendline(
                "sed -i -e 's|ntp-servers, dhcp6.vendor-opts|ntp-servers|' "
                "/etc/dhcp/dhclient.conf"
            )
            self._console.expect(self._shell_prompt)
            self._console.sendline(
                "sed -i '/dhcp6.vendor-opts/d' /etc/dhcp/dhclient.conf"
            )
            self._console.expect(self._shell_prompt)
        else:
            out = self._console.check_output(
                "egrep 'dhcp6.vendor-opts' /etc/dhcp/dhclient.conf"
            )
            if not re.search("request dhcp6.vendor-opts,", out):
                self._console.sendline(
                    "sed -i -e 's|ntp-servers;|ntp-servers, "
                    "dhcp6.vendor-opts; |' /etc/dhcp/dhclient.conf"
                )
                self._console.expect(self._shell_prompt)
                # Enterprise code (3561) 00:00:0D:E9
                # code 11  length 06  (BFVER0) 42:46:56:45:52:30
                # code 13  length 06  (BFCLAN)  42:46:43:4c:41:4e
                encoded_name = str.encode(self.device_name)
                hex_name = iter(binascii.hexlify(encoded_name).decode("utf-8"))
                code_12 = ":".join([f"{j}{k}" for j, k in zip(hex_name, hex_name)])
                len_12 = hex(len(self.device_name)).replace("0x", "").zfill(2)
                option_17 = (
                    "00:00:0D:E9:00:0b:00:06:42:46:56:45:52:30:00:0c:00:"
                    f"{len_12}:{code_12}:00:0d:00:06:42:46:43:4c:41:4e"
                )
                self._console.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
                self._console.sendline(f"send dhcp6.vendor-opts {option_17};")
                self._console.sendline("")
                self._console.sendline("EOF")
                self._console.expect(self._shell_prompt)

    def set_static_ip(
        self, interface: str, ip_address: IPv4Address, netmask: IPv4Address
    ) -> None:
        """Set given static ip for the LAN.

        :param interface: interface name
        :type interface: str
        :param ip_address: static ip address
        :type ip_address: IPv4Address
        :param netmask: netmask
        :type netmask: IPv4Address
        """
        raise NotImplementedError

    def set_default_gw(self, ip_address: IPv4Address, interface: str) -> None:
        """Set given ip address as default gateway address for given interface.

        :param ip_address: gateway ip address
        :type ip_address: IPv4Address
        :param interface: interface name
        :type interface: str
        """
        raise NotImplementedError
