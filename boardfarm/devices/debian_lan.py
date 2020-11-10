# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import ipaddress
import re

import pexpect
import six

from boardfarm.devices.platform import debian
from boardfarm.lib.common import retry_on_exception
from boardfarm.lib.dhcpoption import configure_option
from boardfarm.lib.dns import DNS
from boardfarm.lib.installers import apt_install
from boardfarm.lib.network_helper import valid_ipv4


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
            six.text_type(kwargs.pop("lan_network", "192.168.1.0/24"))
        ).network
        self.lan_gateway = ipaddress.IPv4Interface(
            six.text_type(kwargs.pop("lan_gateway", "192.168.1.1/24"))
        ).ip
        self.dns = DNS(self, {}, {})

    def setup(self, config=None):
        # potential cleanup so this wan device works
        self.sendline("killall iperf ab hping3")
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
        self.sendline("pkill --signal 9 -f dhclient.*%s" % self.iface_dut)
        self.expect(self.prompt)
        apt_install(self, "ndisc6")
        if 0 == self.expect(["Reading package", pexpect.TIMEOUT], timeout=60):
            self.expect(self.prompt, timeout=60)
        else:
            print("Failed to download packages, things might not work")
            self.sendcontrol("c")
            self.expect(self.prompt)

    def start_lan_client(self, wan_gw=None, ipv4_only=False):
        ipv4, ipv6 = None, None
        self.sendline(
            "ip link set down %s && ip link set up %s"
            % (self.iface_dut, self.iface_dut)
        )
        self.expect(self.prompt)

        self.sendline("dhclient -4 -r %s" % self.iface_dut)
        self.expect(self.prompt)
        self.sendline("dhclient -6 -r -i %s" % self.iface_dut)
        self.expect(self.prompt, timeout=60)

        self.sendline("kill $(</run/dhclient6.pid)")
        self.expect(self.prompt)

        self.sendline("kill $(</run/dhclient.pid)")
        self.expect(self.prompt)

        self.sendline("ps aux")
        if self.expect(["dhclient"] + self.prompt) == 0:
            print("WARN: dhclient still running, something started rogue client!")
            self.sendline("pkill --signal 9 -f dhclient.*%s" % self.iface_dut)
            self.expect(self.prompt)

        if not ipv4_only:

            self.disable_ipv6(self.iface_dut)
            self.enable_ipv6(self.iface_dut)
            self.sendline("sysctl -w net.ipv6.conf.%s.accept_dad=0" % self.iface_dut)

            # check if board is providing an RA, if yes use that detail to perform DHCPv6
            # default method used will be statefull DHCPv6
            output = self.check_output("rdisc6 -1 %s" % self.iface_dut, timeout=60)
            M_bit, O_bit = True, True
            if "Prefix" in output:
                M_bit, O_bit = map(
                    lambda x: "Yes" in x, re.findall(r"Stateful.*\W", output)
                )

            # Condition for Stateless DHCPv6, this should update DNS details via DHCP and IP via SLAAC
            if not M_bit and O_bit:
                self.sendline("dhclient -S -v %s" % self.iface_dut)
                if 0 == self.expect([pexpect.TIMEOUT] + self.prompt, timeout=15):
                    self.sendcontrol("c")
                    self.expect(self.prompt)

            # Condition for Statefull DHCPv6, DNS and IP details provided using DHCPv6
            elif M_bit and O_bit:
                self.sendline("dhclient -6 -i -v %s" % self.iface_dut)
                if 0 == self.expect([pexpect.TIMEOUT] + self.prompt, timeout=15):
                    self.sendcontrol("c")
                    self.expect(self.prompt)

            # if env is dual, code should always return an IPv6 address
            # need to actually throw an error, for IPv6 not receiving an IP
            try:
                ipv6 = self.get_interface_ip6addr(self.iface_dut)
            except Exception:
                pass

        self.disable_ipv6("eth0")

        self.sendline("\nifconfig %s 0.0.0.0" % self.iface_dut)
        self.expect(self.prompt)
        self.sendline("rm /var/lib/dhcp/dhclient.leases")
        self.expect(self.prompt)
        self.sendline(
            "sed -e 's/mv -f $new_resolv_conf $resolv_conf/cat $new_resolv_conf > $resolv_conf/g' -i /sbin/dhclient-script"
        )
        self.expect(self.prompt)
        if self.mgmt_dns is not None:
            self.sendline(
                "sed '/append domain-name-servers %s/d' -i /etc/dhcp/dhclient.conf"
                % str(self.mgmt_dns)
            )
            self.expect(self.prompt)
            self.sendline(
                'echo "append domain-name-servers %s;" >> /etc/dhcp/dhclient.conf'
                % str(self.mgmt_dns)
            )
            self.expect(self.prompt)

        self.configure_dhclient((["60", True], ["61", True]))

        # TODO: don't hard code eth0
        self.sendline("ip route del default dev eth0")
        self.expect(self.prompt)
        for _ in range(3):
            try:
                self.sendline("dhclient -4 -v %s" % self.iface_dut)
                if 0 == self.expect(["DHCPOFFER"] + self.prompt, timeout=30):
                    self.expect(self.prompt)
                    break
                else:
                    retry_on_exception(
                        valid_ipv4,
                        (self.get_interface_ipaddr(self.iface_dut),),
                        retries=5,
                    )
                    break
            except Exception:
                self.sendline("killall dhclient")
                self.sendcontrol("c")
        else:
            raise Exception("Error: Device on LAN couldn't obtain address via DHCP.")

        self.sendline("cat /etc/resolv.conf")
        self.expect(self.prompt)
        self.sendline("ip addr show dev %s" % self.iface_dut)
        self.expect(self.prompt)
        self.sendline("ip route")
        # TODO: we should verify this so other way, because the they could be the same subnets
        # in theory
        i = self.expect(
            [
                "default via %s dev %s" % (self.lan_gateway, self.iface_dut),
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
            self.lan_gateway = ipaddress.IPv4Address(six.text_type(self.before.strip()))

            ip_addr = self.get_interface_ipaddr(self.iface_dut)
            self.sendline("ip route | grep %s | awk '{print $1}'" % ip_addr)
            self.expect_exact("ip route | grep %s | awk '{print $1}'" % ip_addr)
            self.expect(self.prompt)
            self.lan_network = ipaddress.IPv4Network(six.text_type(self.before.strip()))
        self.sendline("ip -6 route")
        self.expect(self.prompt)

        # Setup HTTP proxy, so board webserver is accessible via this device
        self.sendline("curl --version")
        self.expect_exact("curl --version")
        self.expect(self.prompt)
        self.sendline("ab -V")
        self.expect(self.prompt)
        self.sendline("nmap --version")
        self.expect(self.prompt)
        self.start_webproxy(self.dante)
        # Write a useful ssh config for routers
        self.sendline("mkdir -p ~/.ssh")
        self.sendline("cat > ~/.ssh/config << EOF")
        self.sendline("Host %s" % self.lan_gateway)
        self.sendline("StrictHostKeyChecking no")
        self.sendline("UserKnownHostsFile=/dev/null")
        self.sendline("")
        self.sendline("Host krouter")
        self.sendline("Hostname %s" % self.lan_gateway)
        self.sendline("StrictHostKeyChecking no")
        self.sendline("UserKnownHostsFile=/dev/null")
        self.sendline("EOF")
        self.expect(self.prompt)
        # Copy an id to the router so people don't have to type a password to ssh or scp
        self.sendline("nc %s 22 -w 1 | cut -c1-3" % self.lan_gateway)
        self.expect_exact("nc %s 22 -w 1 | cut -c1-3" % self.lan_gateway)
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

        if self.install_pkgs_after_dhcp:
            self.install_pkgs()

        if wan_gw is not None and hasattr(self, "lan_fixed_route_to_wan"):
            self.sendline("ip route add %s via %s" % (wan_gw, self.lan_gateway))
            self.expect(self.prompt)
        ipv4 = self.get_interface_ipaddr(self.iface_dut)

        return ipv4, ipv6

    def configure_dhclient(self, dhcpopt):
        """configure dhclient options in lan dhclient.conf

        param dhcpopt: contains list of dhcp options to configure enable or disable
        type dhcpopt: list)
        """
        for opt, enable in dhcpopt:
            configure_option(opt, (self, enable))


if __name__ == "__main__":
    # Example use
    import os
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
