from boardfarm.lib.netstat_parser import NetstatParser
from boardfarm.lib.nw_utility_stub import NwUtilityStub


class DeviceNwUtility(NwUtilityStub):
    def __init__(self, parent_device):
        self.dev = parent_device

    def netstat(self, opts="", extra_opts=""):
        out = self.dev.check_output(f"netstat {opts} {extra_opts}")
        return NetstatParser().parse_inet_output_linux(out)
