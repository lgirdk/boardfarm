import ipaddress
import re
from collections import defaultdict

from boardfarm.lib.linux_nw_utility import NwDnsLookup
from boardfarm.lib.regexlib import (
    AllValidIpv6AddressesRegex,
    ValidIpv4AddressRegex,
)


class DNS:
    """To get the dns IPv4 and IPv6"""

    def __init__(self, device, device_options, aux_options):
        self.device = device
        self.device_options = device_options
        self.aux_options = aux_options

        self.dnsv4 = defaultdict(list)
        self.dnsv6 = defaultdict(list)
        self.auxv4 = None
        self.auxv6 = None
        self.hosts_v4 = defaultdict(list)
        self.hosts_v6 = defaultdict(list)
        self._add_dns_hosts()
        self._add_dnsv6_hosts()
        if self.aux_options:
            self._add_aux_hosts()
            self._add_auxv6_hosts()
        self.hosts_v4.update(self.dnsv4)
        self.hosts_v6.update(self.dnsv6)

        self.nslookup = NwDnsLookup(device)

    def _add_dns_hosts(self):
        if self.device_options:
            final = None
            if "wan-static-ip:" in self.device_options:
                final = str(
                    re.search(
                        "wan-static-ip:" + "(" + ValidIpv4AddressRegex + ")",
                        self.device_options,
                    ).group(1)
                )
            elif hasattr(self.device, "ipaddr"):
                final = str(self.device.ipaddr)
            if final == "localhost":
                if hasattr(self.device, "gw"):
                    final = str(self.device.gw)
                elif hasattr(self.device, "iface_dut"):
                    final = self.device.get_interface_ipaddr(self.device.iface_dut)
                else:
                    final = None
            if final:
                self.dnsv4[self.device.name + ".boardfarm.com"].append(final)

    def _add_dnsv6_hosts(self):
        gwv6 = ipaddress.IPv6Address(
            re.search(
                "wan-static-ipv6:" + "(" + AllValidIpv6AddressesRegex + ")",
                self.device_options,
            ).group(1)
        )
        self.dnsv6[self.device.name + ".boardfarm.com"].append(str(gwv6))

    def _add_aux_hosts(self):
        self.auxv4 = ipaddress.IPv4Address(
            re.search(
                "wan-static-ip:" + "(" + ValidIpv4AddressRegex + ")",
                self.aux_options,
            ).group(1)
        )
        self.dnsv4[self.device.name + ".boardfarm.com"].append(str(self.auxv4))

    def _add_auxv6_hosts(self):
        self.auxv6 = ipaddress.IPv6Address(
            re.search(
                "wan-static-ipv6:" + "(" + AllValidIpv6AddressesRegex + ")",
                self.aux_options,
            ).group(1)
        )
        self.dnsv6[self.device.name + ".boardfarm.com"].append(str(self.auxv6))

    def configure_hosts(self, reachable_ips: int, unreachable_ips: int):
        val_v4 = self.hosts_v4[self.device.name + ".boardfarm.com"][:reachable_ips]
        val_v6 = self.hosts_v6[self.device.name + ".boardfarm.com"][:reachable_ips]
        self.hosts_v4[self.device.name + ".boardfarm.com"] = val_v4
        self.hosts_v6[self.device.name + ".boardfarm.com"] = val_v6
        for val in range(unreachable_ips):
            ipv4 = self.auxv4 + (val + 1)
            ipv6 = self.auxv6 + (val + 1)
            self.hosts_v4[self.device.name + ".boardfarm.com"].append(str(ipv4))
            self.hosts_v6[self.device.name + ".boardfarm.com"].append(str(ipv6))
