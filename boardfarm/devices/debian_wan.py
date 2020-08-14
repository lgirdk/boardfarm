# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import ipaddress

import six
from boardfarm.devices.platform import debian


class DebianWAN(debian.DebianBox):
    model = "debian_wan"
    name = "wan"
    static_route = None
    static_ip = False
    wan_dhcp = False
    wan_dhcpv6 = False
    wan_no_eth0 = False
    wan_dhcp_server = True
    shared_tftp_server = False
    gwv6 = None
    ipv6_prefix = 64

    def __init__(self, *args, **kwargs):
        self.parse_device_options(*args, **kwargs)

        # introducing a hack till json schema does not get updated
        if not self.dev_array:
            self.legacy_add = True
            self.dev_array = "wan_clients"
        self.configure_gw_ip()

    def configure_gw_ip(self):
        if self.gw is None:
            self.gw_ng = ipaddress.IPv4Interface(six.text_type("192.168.0.1/24"))
            self.gw = self.gw_ng.ip
            self.nw = self.gw_ng.network
            self.gw_prefixlen = self.nw.prefixlen

    def setup(self, config):
        self.setup_dnsmasq(config)
        self.sendline("killall iperf ab hping3")
        self.expect(self.prompt)

        # potential cleanup so this wan device works
        self.sendline("iptables -t nat -X")
        self.expect(self.prompt)
        self.sendline("iptables -t nat -F")
        self.expect(self.prompt)

        # set WAN ip address
        if self.wan_dhcp:
            self.sendline("/etc/init.d/isc-dhcp-server stop")
            self.expect(self.prompt)
            self.sendline(
                "dhclient -r %s; dhclient %s" % (self.iface_dut, self.iface_dut)
            )
            self.expect(self.prompt)
            self.gw = self.get_interface_ipaddr(self.iface_dut)
        elif not self.wan_no_eth0:
            self.sendline("ifconfig %s %s" % (self.iface_dut, self.gw_ng))
            self.expect(self.prompt)
            self.sendline("ifconfig %s up" % self.iface_dut)
            self.expect(self.prompt)
            if self.wan_dhcp_server:
                self.setup_dhcp_server()

        if self.wan_dhcpv6:
            # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
            self.sendline("sysctl -w net.ipv6.conf.%s.accept_dad=0" % self.iface_dut)
            self.expect(self.prompt)
            try:
                self.gwv6 = self.get_interface_ip6addr(self.iface_dut)
            except Exception:
                self.sendline("dhclient -6 -i -r %s" % self.iface_dut)
                self.expect(self.prompt)
                self.sendline("dhclient -6 -i -v %s" % self.iface_dut)
                self.expect(self.prompt)
                self.sendline("ip -6 addr")
                self.expect(self.prompt)
                self.gwv6 = self.get_interface_ip6addr(self.iface_dut)
        elif self.gwv6 is not None:
            # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
            self.sendline("sysctl -w net.ipv6.conf.%s.accept_dad=0" % self.iface_dut)
            self.expect(self.prompt)
            self.sendline(
                "ip -6 addr add %s/%s dev %s"
                % (self.gwv6, self.ipv6_prefix, self.iface_dut)
            )
            self.expect(self.prompt)

        # configure routing
        self.sendline("sysctl net.ipv4.ip_forward=1")
        self.expect(self.prompt)
        self.sendline("sysctl net.ipv6.conf.all.forwarding=0")
        self.expect(self.prompt)

        if self.wan_no_eth0 or self.wan_dhcp:
            wan_uplink_iface = self.iface_dut
        else:
            wan_uplink_iface = "eth0"

        wan_ip_uplink = self.get_interface_ipaddr(wan_uplink_iface)
        self.sendline(
            "iptables -t nat -A POSTROUTING -o %s -j SNAT --to-source %s"
            % (wan_uplink_iface, wan_ip_uplink)
        )
        self.expect(self.prompt)

        self.sendline("echo 0 > /proc/sys/net/ipv4/tcp_timestamps")
        self.expect(self.prompt)
        self.sendline("echo 0 > /proc/sys/net/ipv4/tcp_sack")
        self.expect(self.prompt)

        self.sendline("ifconfig %s" % self.iface_dut)
        self.expect(self.prompt)

        self.turn_off_pppoe()

        if self.dante:
            self.start_webproxy(self.dante)

    def setup_dhcp_server(self):

        if not self.wan_dhcp_server:
            return

        # configure DHCP server
        self.sendline("/etc/init.d/isc-dhcp-server stop")
        self.expect(self.prompt)
        self.sendline(
            'sed s/INTERFACES=.*/INTERFACES=\\"%s\\"/g -i /etc/default/isc-dhcp-server'
            % self.iface_dut
        )
        self.expect(self.prompt)
        self.sendline(
            'sed s/INTERFACESv4=.*/INTERFACESv4=\\"%s\\"/g -i /etc/default/isc-dhcp-server'
            % self.iface_dut
        )
        self.expect(self.prompt)
        self.sendline(
            'sed s/INTERFACESv6=.*/INTERFACESv6=\\"%s\\"/g -i /etc/default/isc-dhcp-server'
            % self.iface_dut
        )
        self.expect(self.prompt)
        self.sendline("cat > /etc/dhcp/dhcpd.conf << EOF")
        self.sendline("ddns-update-style none;")
        self.sendline('option domain-name "bigfoot-test";')
        self.sendline("option domain-name-servers %s;" % self.gw)
        self.sendline("default-lease-time 600;")
        self.sendline("max-lease-time 7200;")
        # use the same netmask as the lan device
        self.sendline(
            "subnet %s netmask %s {" % (self.nw.network_address, self.nw.netmask)
        )
        self.sendline(
            "          range %s %s;"
            % (self.nw.network_address + 10, self.nw.network_address + 100)
        )
        self.sendline("          option routers %s;" % self.gw)
        self.sendline("}")
        self.sendline("EOF")
        self.expect(self.prompt)
        self.sendline("/etc/init.d/isc-dhcp-server start")
        self.expect(
            ["Starting ISC DHCP(v4)? server.*dhcpd.", "Starting isc-dhcp-server.*"]
        )
        self.expect(self.prompt)


if __name__ == "__main__":
    # Example use
    try:
        ipaddr, port = sys.argv[1].split(":")
    except Exception:
        raise Exception("First argument should be in form of ipaddr:port")
    dev = DebianWAN(
        ipaddr=ipaddr, color="blue", username="root", password="bigfoot1", port=port
    )
    dev.sendline("echo Hello")
    dev.expect("Hello", timeout=4)
    dev.expect(dev.prompt)

    dev.configure("wan_device")
    if sys.argv[2] == "test_voip":
        sys.path.insert(0, os.getcwd())
        sys.path.insert(0, os.getcwd() + "/tests")
        from boardfarm.lib import installers

        installers.install_asterisk(dev)
