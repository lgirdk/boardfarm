from boardfarm.lib.firewall_parser import iptable_parser
from boardfarm.lib.netstat_parser import NetstatParser
from boardfarm.lib.nw_utility_stub import NwFirewallStub, NwUtilityStub


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
