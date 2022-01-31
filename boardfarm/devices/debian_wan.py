# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.devices.platform import debian
from boardfarm.lib.dns import DNS
from boardfarm.lib.installers import install_tshark
from boardfarm.lib.linux_nw_utility import NwFirewall


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
    auth_dns = False

    def __init__(self, *args, **kwargs):
        self.parse_device_options(*args, **kwargs)

        # introducing a hack till json schema does not get updated
        if not self.dev_array:
            self.legacy_add = True
            self.dev_array = "wan_clients"
        self.dns = DNS(self, kwargs.get("options", {}), kwargs.get("aux_ip", {}))
        self.firewall = NwFirewall(self)

    def setup(self, config):
        self.setup_dnsmasq(config)
        self.modify_dns_hosts(
            {
                "ipv4wan.boardfarm.com": [str(self.gw)],
                "ipv6wan.boardfarm.com": [str(self.gwv6)],
            }
        )
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
            self.sendline(f"dhclient -r {self.iface_dut}; dhclient {self.iface_dut}")
            self.expect(self.prompt)
            self.gw = self.get_interface_ipaddr(self.iface_dut)
        elif not self.wan_no_eth0:
            self.sendline(f"ifconfig {self.iface_dut} {self.gw_ng}")
            self.expect(self.prompt)
            self.sendline(f"ifconfig {self.iface_dut} up")
            self.expect(self.prompt)
            if self.static_route is not None:
                self.send(f"ip route del {self.static_route.split(' via ')[0]}; ")
                self.sendline(f"ip route add {self.static_route}")
                self.expect(self.prompt)
            if self.wan_dhcp_server:
                self.setup_dhcp_server()

        if self.wan_dhcpv6:
            # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
            self.sendline(f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0")
            self.expect(self.prompt)
            try:
                self.gwv6 = self.get_interface_ip6addr(self.iface_dut)
            except Exception:
                self.sendline(f"dhclient -6 -i -r {self.iface_dut}")
                self.expect(self.prompt)
                self.sendline(f"dhclient -6 -i -v {self.iface_dut}")
                self.expect(self.prompt)
                self.sendline("ip -6 addr")
                self.expect(self.prompt)
                self.gwv6 = self.get_interface_ip6addr(self.iface_dut)
        elif self.gwv6 is not None:
            # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
            self.sendline(f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0")
            self.expect(self.prompt)
            self.sendline(
                f"ip -6 addr add {self.gwv6}/{self.ipv6_prefix} dev {self.iface_dut}"
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

        self.sendline(f"ifconfig {self.iface_dut}")
        self.expect(self.prompt)

        self.turn_off_pppoe()

        if self.dante:
            self.start_webproxy(self.dante)
        # Install tshark on wan devices
        install_tshark(self)

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
        self.sendline(f"option domain-name-servers {self.gw};")
        self.sendline("default-lease-time 600;")
        self.sendline("max-lease-time 7200;")
        # use the same netmask as the lan device
        self.sendline(f"subnet {self.nw.network_address} netmask {self.nw.netmask} {{")
        self.sendline(
            "          range %s %s;"
            % (self.nw.network_address + 10, self.nw.network_address + 100)
        )
        self.sendline(f"          option routers {self.gw};")
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
    import os
    import sys

    try:
        ipaddr, port = sys.argv[1].split(":")  # noqa : F821
    except Exception:
        raise Exception("First argument should be in form of ipaddr:port")
    dev = DebianWAN(
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
