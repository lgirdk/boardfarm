from boardfarm.lib.dns_parser import DnsParser
from boardfarm.lib.firewall_parser import iptable_parser
from boardfarm.lib.netstat_parser import NetstatParser
from boardfarm.lib.nw_utility_stub import (
    DHCPStub,
    NwDnsLookupStub,
    NwFirewallStub,
    NwUtilityStub,
)


class DeviceNwUtility(NwUtilityStub):
    def __init__(self, parent_device):
        self.dev = parent_device

    def netstat(self, opts="", extra_opts=""):
        out = self.dev.check_output(f"netstat {opts} {extra_opts}")
        return NetstatParser().parse_inet_output_linux(out)


class NwFirewall(NwFirewallStub):
    def __init__(self, parent_device):
        self.dev = parent_device

    def get_iptables_list(self, opts="", extra_opts=""):
        out = self.dev.check_output(f"iptables {opts} {extra_opts}")
        return iptable_parser().ip6tables(out)

    def is_iptable_empty(self, opts="", extra_opts=""):
        out = self.dev.check_output(f"iptables {opts} {extra_opts}")
        check_out = iptable_parser().ip6tables(out)
        check_empty = (
            True if len([True for i in check_out.values() if i]) == 0 else False
        )
        return check_empty

    def get_ip6tables_list(self, opts="", extra_opts=""):
        out = self.dev.check_output(f"ip6tables {opts} {extra_opts}")
        return iptable_parser().ip6tables(out)

    def is_ip6table_empty(self, opts="", extra_opts=""):
        out = self.dev.check_output(f"ip6tables {opts} {extra_opts}")
        check_out = iptable_parser().ip6tables(out)
        check_empty = (
            True if len([True for i in check_out.values() if i]) == 0 else False
        )
        return check_empty

    def add_drop_rule_iptables(self, option, valid_ip):
        """
        :type option : set -s for source and -d for destination
        :type option : string
        :param valid_ip : dest_ip to be blocked from device
        :type valid_ip : valid ip string
        """
        out = self.dev.check_output(
            "iptables -C INPUT {} {} -j DROP".format(option, valid_ip)
        )
        if "Bad rule" in out:
            self.dev.check_output(
                "iptables -I INPUT 1 {} {} -j DROP".format(option, valid_ip)
            )

    def add_drop_rule_ip6tables(self, option, valid_ip):
        out = self.dev.check_output(
            "ip6tables -C INPUT {} {} -j DROP".format(option, valid_ip)
        )
        if "Bad rule" in out:
            self.dev.check_output(
                "ip6tables -I INPUT 1 {} {} -j DROP".format(option, valid_ip)
            )

    def del_drop_rule_iptables(self, option, valid_ip):
        """
        :type option : set -s for source and -d for destination
        :type option : string
        :param valid_ip : dest_ip to be blocked
        :type valid_ip : valid ip string
        """
        self.dev.check_output(
            "iptables -D INPUT {} {} -j DROP".format(option, valid_ip)
        )

    def del_drop_rule_ip6tables(self, option, valid_ip):
        self.dev.check_output(
            "ip6tables -D INPUT {} {} -j DROP".format(option, valid_ip)
        )


class NwDnsLookup(NwDnsLookupStub):
    def __init__(self, parent_device):
        self.dev = parent_device

    def __call__(self, *args, **kwargs):
        return self.nslookup(*args, **kwargs)

    def nslookup(self, domain_name, opts="", extra_opts=""):
        out = self.dev.check_output(f"nslookup {opts} {domain_name} {extra_opts}")
        return DnsParser().parse_nslookup_output(out)


class DHCP(DHCPStub):
    class DHCPClient(DHCPStub.DHCPClientStub):
        def __init__(self, parent_device):
            self.dev = parent_device

        def dhclient(self, interface, opts="", extra_opts=""):
            return self.dev.check_output(f"dhclient {opts} {interface} {extra_opts}")

    class DHCPServer(DHCPClient):
        """Operation on provisioner"""

        pass

    @staticmethod
    def get_dhcp_object(role, parent_device):
        if role == "client":
            return DHCP.DHCPClient(parent_device)
        if role == "server":
            return DHCP.DHCPServer(parent_device)
