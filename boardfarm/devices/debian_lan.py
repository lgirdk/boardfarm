# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import ipaddress
import logging
import os
import re
import time
from enum import Enum
from functools import cached_property
from typing import List, Optional

import pexpect
from debtcollector import moves
from termcolor import colored

from boardfarm.devices.platform import debian
from boardfarm.exceptions import CodeError
from boardfarm.lib.dhcpoption import configure_option
from boardfarm.lib.dns import DNS
from boardfarm.lib.installers import install_tshark
from boardfarm.lib.linux_nw_utility import Ping
from boardfarm.lib.network_testing import kill_process, tcpdump_capture, tshark_read


class MulticastGroupRecordType(Enum):
    """IGMPv3 Record Types."""

    MODE_IS_INCLUDE = 1
    MODE_IS_EXCLUDE = 2
    CHANGE_TO_INCLUDE_MODE = 3
    CHANGE_TO_EXCLUDE_MODE = 4
    ALLOW_NEW_SOURCES = 5
    BLOCK_OLD_SOURCES = 6


# Add Type Hint support for IGMP Records
MCAST_SOURCE = str
MCAST_GROUP = str
MCAST_GROUP_RECORD = List[
    tuple[List[MCAST_SOURCE], MCAST_GROUP, MulticastGroupRecordType]
]


logger = logging.getLogger("bft")


class DebianLAN(debian.DebianBox):
    model = "debian_lan"
    name = "lan"
    install_pkgs_after_dhcp = False
    wan_no_eth0 = False
    wan_dhcp = False
    is_bridged = False
    static_route = None
    mgmt_dns = "8.8.8.8"
    shared_tftp_server = False

    def __init__(self, *args, **kwargs):
        self.parse_device_options(*args, **kwargs)

        # introducing a hack till json schema does not get updated
        if not self.dev_array:
            self.legacy_add = True
            self.dev_array = "lan_clients"

        self.lan_network = ipaddress.IPv4Interface(
            str(kwargs.pop("lan_network", "192.168.1.0/24"))
        ).network
        self.lan_gateway = ipaddress.IPv4Interface(
            str(kwargs.pop("lan_gateway", "192.168.1.1/24"))
        ).ip
        self.dns = DNS(self, {}, {})
        self.nw_util_ping = Ping(self)
        self.ipv4_client_started = False

    def get_lan_gateway(self):
        self.sendline("ip route list 0/0 | awk '{print $3}'")
        self.expect_exact("ip route list 0/0 | awk '{print $3}'")
        self.expect(self.prompt)
        try:
            return ipaddress.IPv4Address(str(self.before.strip()))
        except ipaddress.AddressValueError:
            logger.warning(
                "Unable to resolve lan client gateway IP. "
                "Did you run boot before tests? "
                "Using default Ziggo address now. (192.168.178.1)"
            )
            return ipaddress.IPv4Address("192.168.178.1")

    def setup(self, config=None):
        self.check_dut_iface()
        # potential cleanup so this wan device works
        self.sendline("killall iperf ab hping3 iperf3")
        self.expect(self.prompt)
        self.sendline("\niptables -t nat -X")
        self.expect("iptables -t")
        self.expect(self.prompt)
        self.sendline("sysctl net.ipv4.ip_forward=1")
        self.expect(self.prompt)
        self.sendline("iptables -t nat -F; iptables -t nat -X")
        self.expect(self.prompt)
        self.sendline("iptables -F; iptables -X")
        self.expect(self.prompt)
        self.sendline(
            "iptables -t nat -A PREROUTING -p tcp --dport 222 -j DNAT --to-destination %s:22"
            % self.lan_gateway
        )
        self.expect(self.prompt)
        self.sendline(
            "iptables -t nat -A POSTROUTING -o %s -p tcp --dport 22 -j MASQUERADE"
            % self.iface_dut
        )
        self.expect(self.prompt)
        self.sendline("echo 0 > /proc/sys/net/ipv4/tcp_timestamps")
        self.expect(self.prompt)
        self.sendline("echo 0 > /proc/sys/net/ipv4/tcp_sack")
        self.expect(self.prompt)
        self.sendline("echo 0 > /proc/sys/net/ipv4/icmp_echo_ignore_broadcasts")
        self.expect(self.prompt)
        self.sendline(f"pkill --signal 9 -f dhclient.*{self.iface_dut}")
        self.expect(self.prompt)

    def prepare_interface(self):
        # bring ip link down and up
        self.sendline(
            f"ip link set down {self.iface_dut} && ip link set up {self.iface_dut}"
        )
        self.expect(self.prompt)

    def __kill_dhclient(self, ipv4=True):
        dhclient_str = f"dhclient {'-4' if ipv4 else '-6'}"

        if ipv4:
            self.release_dhcp(self.iface_dut)
        else:
            self.release_ipv6(self.iface_dut)

        self.sendline("ps aux")
        if self.expect([dhclient_str] + self.prompt) == 0:
            logger.warning(
                "WARN: dhclient still running, something started rogue client!"
            )
            self.sendline(f"pkill --signal 9 -f {dhclient_str}.*{self.iface_dut}")
            self.expect(self.prompt)

        self.sendline(f"kill $(</run/dhclient{'' if ipv4 else 6}.pid)")
        self.expect(self.prompt)

    def configure_docker_iface(self):
        """configure eth0 changes"""
        self.disable_ipv6("eth0")

        # TODO: don't hard code eth0
        self.sendline("ip route del default dev eth0")
        self.expect(self.prompt)

    def start_ipv4_lan_client(self, wan_gw=None, prep_iface=False):
        """restart ipv4 dhclient on lan device"""
        ipv4 = None

        self.check_dut_iface()

        if prep_iface:
            self.prepare_interface()

        self.__kill_dhclient()

        self.sendline(f"\nifconfig {self.iface_dut} 0.0.0.0")
        self.expect(self.prompt)
        self.sendline("rm /var/lib/dhcp/dhclient.leases")
        self.expect(self.prompt)
        # TODO: remove the whole thing once LAN image is cleaned up.
        if self.mgmt_dns is not None:
            self.sendline(
                "sed '/append domain-name-servers %s/d' -i /etc/dhcp/dhclient.conf"
                % str(self.mgmt_dns)
            )
            self.expect(self.prompt)
        self.configure_dhclient((["60", True], ["61", True]))

        install_tshark(self)
        build_tag = os.getenv("BUILD_TAG", "")
        now = time.strftime("%Y%m%d_%H%M%S")
        capture_file = build_tag + "_" + now + "_lan_dhcp_capture.pcap"
        tcpdump_capture(self, self.iface_dut, capture_file=capture_file, port="67-68")
        self.tshark_process = True
        for _ in range(5):
            try:
                self.renew_dhcp(self.iface_dut)
                ipv4 = self.get_interface_ipaddr(self.iface_dut)
                break
            except Exception:
                self.__kill_dhclient()
                self.sendcontrol("c")
                self.expect_prompt()
        else:
            kill_process(self, "tcpdump")
            self.tshark_process = False
            tshark_logs = tshark_read(self, capture_file, timeout=120)

            raise Exception(
                f"""Error: Device on LAN couldn't obtain address via DHCP.
            #########################################
            #######TShark Logs for DHCP Starts#######
            #########################################
            {tshark_logs}
            #########################################
            ########TShark Logs for DHCP Ends########
            #########################################"""
            )

        if self.tshark_process:
            kill_process(self, "tcpdump")
            self.tshark_process = False
            self.sudo_sendline(f"rm {capture_file}")

        self.sendline("cat /etc/resolv.conf")
        self.expect(self.prompt)
        self.sendline(f"ip addr show dev {self.iface_dut}")
        self.expect(self.prompt)
        self.sendline("ip route")
        # TODO: we should verify this so other way, because the they could be the same subnets
        # in theory
        i = self.expect(
            [
                f"default via {self.lan_gateway} dev {self.iface_dut}",
                pexpect.TIMEOUT,
            ],
            timeout=5,
        )
        if i == 1:
            # bridged mode
            self.is_bridged = True
            # update gw
            self.sendline("ip route list 0/0 | awk '{print $3}'")
            self.expect_exact("ip route list 0/0 | awk '{print $3}'")
            self.expect(self.prompt)
            self.lan_gateway = ipaddress.IPv4Address(str(self.before.strip()))

            ip_addr = self.get_interface_ipaddr(self.iface_dut)
            self.sendline("ip route | grep %s | awk '{print $1}'" % ip_addr)
            self.expect_exact("ip route | grep %s | awk '{print $1}'" % ip_addr)
            self.expect(self.prompt)
            self.lan_network = ipaddress.IPv4Network(str(self.before.strip()))

        if wan_gw is not None and hasattr(self, "lan_fixed_route_to_wan"):
            self.sendline(f"ip route add {wan_gw} via {self.lan_gateway}")
            self.expect(self.prompt)
        ipv4 = self.get_interface_ipaddr(self.iface_dut)

        if ipv4:
            self.ipv4_client_started = True

        return ipv4

    def start_ipv6_lan_client(self, wan_gw=None, prep_iface=False):
        """restart ipv6 dhclient on lan device"""
        ipv6 = None

        self.check_dut_iface()

        if prep_iface:
            self.prepare_interface()

        self.__kill_dhclient(False)

        self.disable_ipv6(self.iface_dut)
        self.enable_ipv6(self.iface_dut)
        self.sendline(f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0")

        # check if board is providing an RA, if yes use that detail to perform DHCPv6
        # default method used will be statefull DHCPv6
        output = self.check_output(f"rdisc6 -1 {self.iface_dut}", timeout=60)
        M_bit, O_bit = True, True
        if "Prefix" in output:
            M_bit, O_bit = map(
                lambda x: "Yes" in x, re.findall(r"Stateful.*\W", output)
            )
        # if env is dual, code should always return an IPv6 address
        install_tshark(self)
        build_tag = os.getenv("BUILD_TAG", "")
        now = time.strftime("%Y%m%d_%H%M%S")
        capture_file = build_tag + "_" + now + "_lan_dhcpv6_capture.pcap"
        tcpdump_capture(self, self.iface_dut, capture_file=capture_file, port="546-547")
        self.tshark_process = True
        for _ in range(5):
            try:
                # Condition for Stateless DHCPv6, this should update DNS details via DHCP and IP via SLAAC
                if not M_bit and O_bit:
                    self.renew_ipv6(self.iface_dut, stateless=True)
                elif M_bit and O_bit:
                    self.renew_ipv6(self.iface_dut)
                ipv6 = self.get_interface_ip6addr(self.iface_dut)
                break
            except Exception:
                self.__kill_dhclient()
                self.sendcontrol("c")
                self.expect_prompt()
        else:
            kill_process(self, "tcpdump")
            self.tshark_process = False
            tshark_logs = tshark_read(self, capture_file, timeout=120)

            raise Exception(
                f"""Error: Device on LAN couldn't obtain IPV6 address via DHCPV6.
            #########################################
            #######TShark Logs for DHCPV6 Starts#######
            #########################################
            {tshark_logs}
            #########################################
            ########TShark Logs for DHCPV6 Ends########
            #########################################"""
            )

        if self.tshark_process:
            kill_process(self, "tcpdump")
            self.tshark_process = False
            self.sudo_sendline(f"rm {capture_file}")

        return ipv6

    @moves.moved_method("start_ipv6_lan_client & start_ipv4_lan_client")
    def start_lan_client(self, wan_gw=None, ipv4_only=False):
        ipv4, ipv6 = None, None

        self.configure_docker_iface()
        self.prepare_interface()

        if not ipv4_only:
            ipv6 = self.start_ipv6_lan_client(wan_gw)

        ipv4 = self.start_ipv4_lan_client(wan_gw)

        self.configure_proxy_pkgs()

        return ipv4, ipv6

    def configure_proxy_pkgs(self):
        self.__start_http_proxy()
        self.__add_ssh_proxy()
        self.__passwordless_setting()

        if self.install_pkgs_after_dhcp:
            self.install_pkgs()

    def __start_http_proxy(self):
        """Setup HTTP proxy, so board webserver is accessible via this device"""
        self.sendline("curl --version")
        self.expect_exact("curl --version")
        self.expect(self.prompt)
        self.sendline("ab -V")
        self.expect(self.prompt)
        self.sendline("nmap --version")
        self.expect(self.prompt)
        self.start_webproxy(self.dante)

    def __add_ssh_proxy(self):
        """Write a useful ssh config for routers"""
        self.sendline("mkdir -p ~/.ssh")
        self.sendline("cat > ~/.ssh/config << EOF")
        self.sendline(f"Host {self.lan_gateway}")
        self.sendline("StrictHostKeyChecking no")
        self.sendline("UserKnownHostsFile=/dev/null")
        self.sendline("")
        self.sendline("Host krouter")
        self.sendline(f"Hostname {self.lan_gateway}")
        self.sendline("StrictHostKeyChecking no")
        self.sendline("UserKnownHostsFile=/dev/null")
        self.sendline("EOF")
        self.expect(self.prompt)

    def __passwordless_setting(self):
        """Copy an id to the router so people don't have to type a password to ssh or scp"""
        self.sendline(f"nc {self.lan_gateway} 22 -w 1 | cut -c1-3")
        self.expect_exact(f"nc {self.lan_gateway} 22 -w 1 | cut -c1-3")
        if 0 == self.expect(["SSH"] + self.prompt, timeout=5) and not self.is_bridged:
            self.sendcontrol("c")
            self.expect(self.prompt)
            self.sendline(
                '[ -e /root/.ssh/id_rsa ] || ssh-keygen -N "" -f /root/.ssh/id_rsa'
            )
            if 0 != self.expect(["Protocol mismatch."] + self.prompt):
                self.sendline(
                    "\nscp ~/.ssh/id_rsa.pub %s:/etc/dropbear/authorized_keys"
                    % self.lan_gateway
                )
                self.expect("_keys")
                if 0 == self.expect(["assword:"] + self.prompt):
                    self.sendline("password")
                    self.expect(self.prompt)
        else:
            self.sendcontrol("c")
            self.expect(self.prompt)

    def configure_dhclient(self, dhcpopt):
        """configure dhclient options in lan dhclient.conf

        param dhcpopt: contains list of dhcp options to configure enable or disable
        type dhcpopt: list)
        """
        for opt, enable in dhcpopt:
            configure_option(opt, (self, enable))

    def check_dut_iface(self):
        output = super().check_dut_iface()
        if "NO-CARRIER" in output:
            msg = colored(
                f"{self.name}: {self.iface_dut} CARRIER DOWN\n{output}",
                color="red",
                attrs=["bold"],
            )
            logger.error(msg)
        return output

    def send_igmpv3_report(
        self, mcast_group_record: MCAST_GROUP_RECORD, count: int
    ) -> None:
        """Send an IGMPv3 report with desired multicast record.

        Multicast source and group must be IPv4 addresses.
        Multicast sources need to be non-multicast addresses and
        group address needs to be a multicast address.

        Implementation relies on a custom send_igmp_report
        script based on scapy.

        :param mcast_group_record: IGMPv3 multicast group record
        :type mcast_group_record: MCAST_GROUP_RECORD
        :param count: num of packets to send in 1s interval
        :type count: int
        :raises CodeError: if send_igmp_report command fails
        """
        command = f"send_igmp_report -i {self.iface_dut} -c {count}"
        out = self._send_multicast_report(command, mcast_group_record)
        if f"Sent {count} packets" not in out:
            raise CodeError(f"Failed to execute send_mld_report command:\n{out}")

    def send_mldv2_report(self, mcast_group_record: MCAST_GROUP_RECORD, count: int):
        """Send an MLDv2 report with desired multicast record.

        Multicast source and group must be IPv6 addresses.
        Multicast sources need to be non-multicast addresses and
        group address needs to be a multicast address.

        Implementation relies on a custom send_mld_report
        script based on scapy.

        :param mcast_group_record: MLDv2 multicast group record
        :type mcast_group_record: MCAST_GROUP_RECORD
        :param count: num of packets to send in 1s interval
        :type count: int
        :raises CodeError: if send_mld_report command fails
        """
        command = f"send_mld_report -i {self.iface_dut} -c {count}"
        out = self._send_multicast_report(command, mcast_group_record)
        if f"Sent {count} packets" not in out:
            raise CodeError(f"Failed to execute send_mld_report command:\n{out}")

    def _send_multicast_report(
        self, command: str, mcast_group_record: MCAST_GROUP_RECORD
    ) -> str:
        args = ""
        for sources, group, rtype in mcast_group_record:
            src = ",".join(sources)
            args += f'-mr "{src};{group};{rtype.value} "'

        out = self.check_output(f"{command} {args}")
        if "Traceback" in out:
            raise CodeError(f"Failed to send the report!!\n{self.before}")
        return out

    @cached_property
    def ip_addr(self) -> str:
        """Return the IPv4 address on IFACE facing DUT.

        :return: IPv4 address in string format.
        :rtype: str
        """
        return self.get_interface_ipaddr(self.iface_dut)

    @cached_property
    def ip6_addr(self) -> str:
        """Return the IPv6 address on IFACE facing DUT.

        :return: IPv6 address in string format.
        :rtype: str
        """
        return self.get_interface_ip6addr(self.iface_dut)

    @cached_property
    def gw_mac_addr(self) -> str:
        """Return the L2 address of DUT gateway from ARP table.

        :return: MAC address in string format.
        :rtype: str
        """
        # must only be called post boot.
        route = self.check_output("ip route show default")
        gw_ip = re.findall(r"default via (.*) dev", route)[0]
        out = self.check_output(f"arp -i {self.iface_dut} -a")
        return re.findall(rf"\({gw_ip}\) at\s(.*)\s\[", out)[0]

    @cached_property
    def mac_addr(self) -> str:
        """Return the L2 address of IFACE facing DUT.

        :return: MAC address in string format.
        :rtype: str
        """
        return self.get_interface_macaddr(self.iface_dut)

    def clear_cache(self):
        """To clear all the cached properties."""
        self.__dict__.pop("ip_addr", None)
        self.__dict__.pop("ip6_addr", None)
        self.__dict__.pop("gw_mac_addr", None)
        self.__dict__.pop("mac_addr", None)


if __name__ == "__main__":
    # Example use
    import sys

    try:
        ipaddr, port = sys.argv[1].split(":")  # noqa : F821
    except Exception:
        raise Exception("First argument should be in form of ipaddr:port")
    dev = DebianLAN(
        ipaddr=ipaddr, color="blue", username="root", password="bigfoot1", port=port
    )
    dev.sendline("echo Hello")
    dev.expect("Hello", timeout=4)
    dev.expect(dev.prompt)

    dev.configure()
    if sys.argv[2] == "test_voip":  # noqa : F821
        sys.path.insert(0, os.getcwd())  # noqa : F821
        sys.path.insert(0, os.getcwd() + "/tests")  # noqa : F821
        from boardfarm.lib import installers

        installers.install_asterisk(dev)
