import re
from typing import Union

from boardfarm.exceptions import CodeError
from boardfarm.lib.dns_parser import DnsParser
from boardfarm.lib.firewall_parser import iptable_parser
from boardfarm.lib.netstat_parser import NetstatParser
from boardfarm.lib.network_testing import kill_process, tcpdump_capture, tcpdump_read
from boardfarm.lib.nw_utility_stub import (
    DHCPStub,
    NwDnsLookupStub,
    NwFirewallStub,
    NwUtilityStub,
    PingStub,
)


class DeviceNwUtility(NwUtilityStub):
    def __init__(self, parent_device):
        self.dev = parent_device

    def netstat(self, opts="", extra_opts=""):
        out = self.dev.check_output(f"netstat {opts} {extra_opts}")
        return NetstatParser().parse_inet_output_linux(out)

    def start_tcpdump(self, fname: str, interface: str, filters: str = "") -> str:
        """Starts a tcpdump capture on the shell prompt of the linux console

        Args:
            fname (str): name of the pcap file
            interface (str): interface at which the tcp traffic listens to
            filters (str, optional): additional filters to add into the command. Defaults to ""

        Returns:
            str: return the process id of the tcpdump capture
        """
        return tcpdump_capture(
            self.dev,
            interface,
            capture_file=fname,
            return_pid=True,
            additional_filters=f"-s0 {filters}",
        )

    def stop_tcpdump(self, pid: str) -> None:
        """Kills the tcpdump process using the process id

        Args:
            pid (str): process id
        """
        kill_process(self.dev, process="tcpdump", pid=pid)

    def read_tcpdump(
        self,
        capture_file: str,
        protocol: str = "",
        opts: str = "",
        timeout: int = 30,
        rm_pcap: bool = True,
    ) -> str:
        """Read the tcpdump packets and deletes the capture file after read if required

        Args:
            capture_file (str): Filename in which the packets were captured
            protocol (str, optional): protocol to filter. Defaults to "".
            opts (str, optional):  can be more than one parameter but it should be joined with "and" eg: ('host '+dest_ip+' and port '+port). Defaults to "".
            timeout (int, optional): timeout after executing the tcpdump read; default 30 seconds. Defaults to 30.
            rm_pcap (bool, optional):  Argument determining if the pcap file needs to be removed. Defaults to True.

        Returns:
            str: Output of tcpdump read command in json format
        """
        return tcpdump_read(
            self.dev,
            capture_file,
            protocol=protocol,
            opts=opts,
            timeout=timeout,
            rm_pcap=rm_pcap,
        )

    def scp(
        self,
        ip: str,
        port: Union[int, str],
        user: str,
        pwd: str,
        source_path: str,
        dest_path: str,
        action: str,
    ) -> None:
        """Allows you to securely copy files and directories between the linux device and the remote host

        Args:
            ip (str): ip address of the host
            port (Union[int, str]): port number of the host
            user (str): username of the host login
            pwd (str): password of the host login
            source_path (str): path of the source of the file
            dest_path (str): path of the destination of the file
            action (str): scp action to perform i.e upload, download
        """
        self.dev.scp(
            host=ip,
            port=port,
            username=user,
            password=pwd,
            src_path=source_path,
            dst_path=dest_path,
            action=action,
        )

    def traceroute_host(
        self, host_ip: str, version: str = "", options: str = ""
    ) -> str:
        """Runs a Traceroute command on linux console to a host ip and returns the route packets take to a network host

        Args:
            host_ip (str): ip address of the host
            version (str): Version of the traceroute command. Defaults to "".
            options (str): Additional options in the command. Defaults to "".

        Returns:
            str: Return the entire route to the host ip from linux device
        """
        return self.dev.traceroute(host_ip, version=version, options=options)


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
        out = self.dev.check_output(f"iptables -C INPUT {option} {valid_ip} -j DROP")
        if re.search(rf"host\/network.*{valid_ip}.*not found", out):
            raise CodeError(
                f"Firewall rule cannot be added as the ip address: {valid_ip} could not be found"
            )
        if "Bad rule" in out:
            self.dev.check_output(f"iptables -I INPUT 1 {option} {valid_ip} -j DROP")

    def add_drop_rule_ip6tables(self, option, valid_ip):
        out = self.dev.check_output(f"ip6tables -C INPUT {option} {valid_ip} -j DROP")
        if re.search(rf"host\/network.*{valid_ip}.*not found", out):
            raise CodeError(
                f"Firewall rule cannot be added as the ip address: {valid_ip} could not be found"
            )
        if "Bad rule" in out:
            self.dev.check_output(f"ip6tables -I INPUT 1 {option} {valid_ip} -j DROP")

    def del_drop_rule_iptables(self, option, valid_ip):
        """
        :type option : set -s for source and -d for destination
        :type option : string
        :param valid_ip : dest_ip to be blocked
        :type valid_ip : valid ip string
        """
        self.dev.check_output(f"iptables -D INPUT {option} {valid_ip} -j DROP")

    def del_drop_rule_ip6tables(self, option, valid_ip):
        self.dev.check_output(f"ip6tables -D INPUT {option} {valid_ip} -j DROP")


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


class Ping(PingStub):
    def __init__(self, parent_device):
        self.dev = parent_device

    def ping_background(self, ip, opts):
        output = self.dev.check_output(f"ping {opts} {ip} > ping.txt &")
        return re.search(r"(\[\d{1,10}\]\s(\d{1,6}))", output).group(2)

    def loss_percentage(self, pid):
        output = self.dev.check_output(f"kill -3 {pid}")
        return re.search(r"(\d+)% loss", output).group(1)

    def kill_ping_background(self, pid):
        # SIGINT is used to get the ping statistics fetch it if any test required
        self.dev.check_output(f"kill -2 {pid}")
        return True
