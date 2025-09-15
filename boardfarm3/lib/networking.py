"""Boardfarm networking module."""

from __future__ import annotations

import re
from collections import defaultdict
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import TYPE_CHECKING, Any, Literal, Protocol

import pexpect
from bs4 import BeautifulSoup
from jc.parsers import dig

from boardfarm3.exceptions import SCPConnectionError, UseCaseFailure
from boardfarm3.lib.parsers.iptables_parser import IptablesParser
from boardfarm3.lib.parsers.nslookup_parser import NslookupParser
from boardfarm3.templates.cpe import CPE

if TYPE_CHECKING:
    from boardfarm3.templates.cpe import CPESW
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN


class _LinuxConsole(Protocol):
    """Linux console protocol."""

    def execute_command(self, command: str, timeout: int = -1) -> str:
        """Execute given command in the rg-console and return output.

        :param command: command to execute
        :type command: str
        :param timeout: timeout in seconds. Defaults to -1
        :type timeout: int
        """

    def sendline(self, string: str) -> None:
        """Send given string to the console.

        :param string: string to send
        """

    def expect(self, pattern: str | list[str], timeout: int = -1) -> int:
        """Wait for given regex pattern(s) and return the match index.

        :param pattern: expected regex pattern or pattern list
        :type pattern: Union[str, List[str]]
        :param timeout: timeout in seconds. Defaults to -1
        :type timeout: int
        """

    def expect_exact(self, pattern: str | list[str], timeout: int = -1) -> int:
        """Wait for given exact pattern(s) and return the match index.

        :param pattern: expected pattern or pattern list
        :type pattern: Union[str, List[str]]
        :param timeout: timeout in seconds. Defaults to -1
        :type timeout: int
        """


def start_tcpdump(  # noqa: PLR0913
    console: _LinuxConsole,
    interface: str,
    port: str | None,
    output_file: str = "pkt_capture.pcap",
    filters: dict | None = None,
    additional_filters: str | None = "",
) -> str:
    """Start tcpdump capture on given interface.

    :param console: console or device instance
    :type console: _LinuxConsole
    :param interface: inteface name where packets to be captured
    :type interface: str
    :param port: port number, can be a range of ports(eg: 443 or 433-443)
    :type port: str
    :param output_file: pcap file name, Defaults: pkt_capture.pcap
    :type output_file: str
    :param filters: filters as key value pair(eg: {"-v": "", "-c": "4"})
    :type filters: Optional[Dict]
    :param additional_filters: additional filters
    :type additional_filters: Optional[str]
    :raises ValueError: on failed to start tcpdump
    :return: console ouput and tcpdump process id
    :rtype: str
    """
    command = f"tcpdump -U -i {interface} -n -w {output_file} "
    filter_str = (
        " ".join([" ".join(i) for i in filters.items()]) if filters is not None else ""
    )
    filter_str += additional_filters
    if port:
        output = console.execute_command(f"{command} 'portrange {port}' {filter_str} &")
    else:
        output = console.execute_command(f"{command} {filter_str} &")
    if console.expect_exact([f"tcpdump: listening on {interface}", pexpect.TIMEOUT]):
        msg = f"Failed to start tcpdump on {interface}"
        raise ValueError(msg)
    return re.search(r"(\[\d+\]\s(\d+))", output)[2]


def stop_tcpdump(console: _LinuxConsole, process_id: str) -> None:
    """Stop tcpdump capture.

    :param console: linux console or device instance
    :type console: _LinuxConsole
    :param process_id: tcpdump process id
    :type process_id: str
    :raises ValueError: on failed to stop tcpdump process
    """
    output = console.execute_command(f"kill {process_id}")
    if "packets captured" not in output:
        idx = console.expect_exact(["captured", pexpect.TIMEOUT])
        if idx:
            msg = f"Failed to stop tcpdump process with PID {process_id}"
            raise ValueError(msg)
    console.execute_command("sync")


def tcpdump_read(  # noqa: PLR0913
    console: _LinuxConsole,
    capture_file: str,
    protocol: str = "",
    opts: str = "",
    timeout: int = 30,
    rm_pcap: bool = True,
) -> str:
    """Read the given tcpdump and delete the file afterwards.

    :param console: linux device or console instance
    :type console: _LinuxConsole
    :param capture_file: pcap file path
    :type capture_file: str
    :param protocol: protocol to the filter
    :type protocol: str
    :param opts: command line options for reading pcap
    :type opts: str
    :param timeout: timeout in seconds for reading pcap
    :type timeout: int
    :param rm_pcap: romove pcap file afterwards
    :type rm_pcap: bool
    :return: tcpdump output
    :rtype: str
    """
    if opts:
        protocol = f"{protocol} and {opts}"
    tcpdump_output = console.execute_command(
        f"tcpdump -n -r {capture_file} {protocol}",
        timeout=timeout,
    )
    if rm_pcap:
        console.execute_command(f"rm {capture_file}")
    return tcpdump_output


def scp(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    console: _LinuxConsole,
    host: str,
    port: int | str,
    username: str,
    password: str,
    src_path: str,
    dst_path: str,
    action: Literal["download", "upload"] = "download",
    timeout: int = 30,
) -> None:
    """SCP file.

    :param console: linux device or console instance
    :type console: _LinuxConsole
    :param host: remote ssh host ip address
    :type host: str
    :param port: remove ssh host port number
    :type port: Union[int, str]
    :param username: ssh username
    :type username: str
    :param password: ssh password
    :type password: str
    :param src_path: source file path
    :type src_path: str
    :param dst_path: destination path
    :type dst_path: str
    :param action: scp action(download/upload), defaults to "download"
    :type action: Literal["download", "upload"], optional
    :param timeout: scp timeout in seconds, defaults to 30
    :type timeout: int
    :raises SCPConnectionError: on failed to scp file
    """
    host = host if isinstance(ip_address(host), IPv4Address) else f"[{host}]"
    if action == "download":
        command = (
            "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            f" -P {port} {username}@{host}:{src_path} {dst_path}"
        )
    else:
        command = (
            "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            f" -P {port} {src_path} {username}@{host}:{dst_path}"
        )
    console.sendline(command)
    if console.expect([pexpect.TIMEOUT, "continue connecting?"], timeout=10):
        console.sendline("y")
    if console.expect([pexpect.TIMEOUT, "assword:"], timeout=10):
        console.sendline(password)
    if console.expect_exact(["100%", pexpect.TIMEOUT], timeout=timeout):
        msg = f"Failed to scp from {src_path} to {dst_path}"
        raise SCPConnectionError(msg)


def traceroute_host(
    console: _LinuxConsole,
    host_ip: str,
    version: str = "",
    options: str = "",
) -> str:
    """Traceroute given host ip and return the details.

    :param console: linux device or console instance
    :type console: _LinuxConsole
    :param host_ip: host ip address
    :type host_ip: str
    :param version: ip version
    :type version: str
    :param options: additional command line options
    :type options: str
    :return: traceroute command output
    :rtype: str
    """
    return console.execute_command(
        f"traceroute{version} {options} {host_ip}",
        timeout=90,
    )


class IptablesFirewall:
    """Linux iptables firewall."""

    def __init__(self, console: _LinuxConsole) -> None:
        """Initialize IptablesFirewall.

        :param console: linux console or device instance
        :type console: _LinuxConsole
        """
        self._console = console

    def get_iptables_list(
        self,
        opts: str = "",
        extra_opts: str = "",
    ) -> dict[str, list[dict]]:
        """Return iptables rules as dictionary.

        :param opts: command line arguments for iptables command
        :type opts: str
        :param extra_opts: extra command line arguments for iptables command
        :type extra_opts: str
        :return: iptables rules dictionary
        :rtype: Dict[str, List[Dict]]
        """
        return IptablesParser().iptables(
            self._console.execute_command(f"iptables {opts} {extra_opts}"),
        )

    def is_iptable_empty(self, opts: str = "", extra_opts: str = "") -> bool:
        """Return True if iptables is empty.

        :param opts: command line arguments for iptables command
        :type opts: str
        :param extra_opts: extra command line arguments for iptables command
        :type extra_opts: str
        :return: True if iptables is empty, False otherwise
        :rtype: bool
        """
        return not any(self.get_iptables_list(opts, extra_opts).values())

    def get_ip6tables_list(
        self,
        opts: str = "",
        extra_opts: str = "",
    ) -> dict[str, list[dict]]:
        """Return ip6tables rules as dictionary.

        :param opts: command line arguments for ip6tables command
        :type opts: str
        :param extra_opts: extra command line arguments for ip6tables command
        :type extra_opts: str
        :return: ip6tables rules dictionary
        :rtype: Dict[str, List[Dict]]
        """
        return IptablesParser().ip6tables(
            self._console.execute_command(f"ip6tables {opts} {extra_opts}"),
        )

    def get_iptables_policy(
        self,
        opts: str = "",
        extra_opts: str = "-nvL --line-number",
    ) -> dict[str, str]:
        """Return iptables policies as dictionary.

        :param opts: command line arguments for iptables command
        :type opts: str
        :param extra_opts: options for iptables command, defaults to -nvL --line-number
        :type extra_opts: str
        :return: iptables policies dictionary
        :rtype: dict[str, str]
        """
        return IptablesParser().iptables_policy(
            self._console.execute_command(f"iptables {opts} {extra_opts}"),
        )

    def get_ip6tables_policy(
        self,
        opts: str = "",
        extra_opts: str = "-nvL --line-number",
    ) -> dict[str, str]:
        """Return ip6tables policies as dictionary.

        :param opts: command line arguments for iptables command
        :type opts: str
        :param extra_opts: options for iptables command, defaults to -nvL --line-number
        :type extra_opts: str
        :return: iptables policies dictionary
        :rtype: dict[str, str]
        """
        return IptablesParser().iptables_policy(
            self._console.execute_command(f"ip6tables {opts} {extra_opts}"),
        )

    def is_ip6table_empty(self, opts: str = "", extra_opts: str = "") -> bool:
        """Return True if ip6tables is empty.

        :param opts: command line arguments for ip6tables command
        :type opts: str
        :param extra_opts: extra command line arguments for ip6tables command
        :type extra_opts: str
        :return: True if ip6tables is empty, False otherwise
        :rtype: bool
        """
        return not any(self.get_ip6tables_list(opts, extra_opts).values())

    def add_drop_rule_iptables(self, option: str, valid_ip: str) -> None:
        """Add drop rule to iptables.

        :param option: iptables command line options
        :type option: str
        :param valid_ip: ip to be blocked from device
        :type valid_ip: str
        :raises ValueError: on given iptables rule can't be added
        """
        iptables_output = self._console.execute_command(
            f"iptables -C INPUT {option} {valid_ip} -j DROP",
        )
        if "Bad rule" in iptables_output:
            self._console.execute_command(
                f"iptables -I INPUT 1 {option} {valid_ip} -j DROP",
            )
        if re.search(rf"host\/network.*{valid_ip}.*not found", iptables_output):
            msg = (
                "Firewall rule cannot be added as the ip address: "
                f"{valid_ip} could not be found"
            )
            raise ValueError(
                msg,
            )

    def add_drop_rule_ip6tables(self, option: str, valid_ip: str) -> None:
        """Add drop rule to ip6tables.

        :param option: ip6tables command line options
        :type option: str
        :param valid_ip: ip to be blocked from device
        :type valid_ip: str
        :raises ValueError: on given ip6tables rule can't be added
        """
        ip6tables_output = self._console.execute_command(
            f"ip6tables -C INPUT {option} {valid_ip} -j DROP",
        )
        if "Bad rule" in ip6tables_output:
            self._console.execute_command(
                f"ip6tables -I INPUT 1 {option} {valid_ip} -j DROP",
            )
        if re.search(rf"host\/network.*{valid_ip}.*not found", ip6tables_output):
            msg = (
                "Firewall rule cannot be added as the ip address: "
                f"{valid_ip} could not be found"
            )
            raise ValueError(
                msg,
            )

    def del_drop_rule_iptables(self, option: str, valid_ip: str) -> None:
        """Delete drop rule from iptables.

        :param option: iptables command line options
        :type option: str
        :param valid_ip: ip to be unblocked
        :type valid_ip: str
        """
        self._console.execute_command(f"iptables -D INPUT {option} {valid_ip} -j DROP")

    def del_drop_rule_ip6tables(self, option: str, valid_ip: str) -> None:
        """Delete drop rule from ip6tables.

        :param option: ip6tables command line options
        :type option: str
        :param valid_ip: ip to be unblocked
        :type valid_ip: str
        """
        self._console.execute_command(f"ip6tables -D INPUT {option} {valid_ip} -j DROP")


class NSLookup:
    """NSLookup command line utility."""

    def __init__(self, console: _LinuxConsole) -> None:
        """Initialize NSLookup.

        :param console: console or device instance
        :type console: _LinuxConsole
        """
        self._hw = console

    def __call__(
        self,
        domain_name: str,
        opts: str = "",
        extra_opts: str = "",
    ) -> dict[str, Any]:
        """Run nslookup with given arguments and return the parsed results.

        :param domain_name: domain name to perform nslookup on
        :type domain_name: str
        :param opts: nslookup command line options
        :type opts: str
        :param extra_opts: nslookup additional command line options
        :type extra_opts: str
        :return: parsed nslookup results as dictionary
        :rtype: Dict[str, Any]
        """
        return self.nslookup(domain_name, opts, extra_opts)

    def nslookup(
        self,
        domain_name: str,
        opts: str = "",
        extra_opts: str = "",
    ) -> dict[str, Any]:
        """Run nslookup with given arguments and return the parsed results.

        :param domain_name: domain name to perform nslookup on
        :type domain_name: str
        :param opts: nslookup command line options
        :type opts: str
        :param extra_opts: nslookup additional command line options
        :type extra_opts: str
        :return: parsed nslookup results as dictionary
        :rtype: Dict[str, Any]
        """
        return NslookupParser().parse_nslookup_output(
            self._hw.execute_command(f"nslookup {opts} {domain_name} {extra_opts}"),
        )


# pylint: disable=too-few-public-methods,too-many-instance-attributes
class DNS:
    """Holds DNS names and their addresses."""

    # pylint: disable=too-many-arguments
    def __init__(  # noqa: PLR0913
        self,
        console: _LinuxConsole,
        device_name: str,
        ipv4_address: str | None = None,
        ipv6_address: str | None = None,
        ipv4_aux_address: IPv4Address | None = None,
        ipv6_aux_address: IPv6Address | None = None,
        aux_url: str | None = None,
    ) -> None:
        """Initialize DNS.

        :param console: console or device instance
        :type console: _LinuxConsole
        :param device_name: device name
        :type device_name: str
        :param ipv4_address: ipv4 address of the device
        :type ipv4_address: str
        :param ipv6_address: ipv6 address of the device
        :type ipv6_address: str
        :param ipv4_aux_address: ipv4 aux address
        :type ipv4_aux_address: IPv4Address
        :param ipv6_aux_address: ipv6 aux address
        :type ipv6_aux_address: IPv6Address
        :param aux_url: aux url
        :type aux_url: str
        """
        self.auxv4 = ipv4_aux_address
        self.auxv6 = ipv6_aux_address
        self.dnsv4: defaultdict = defaultdict(list)
        self.dnsv6: defaultdict = defaultdict(list)
        self.hosts_v4: defaultdict = defaultdict(list)
        self.hosts_v6: defaultdict = defaultdict(list)
        self.fqdn = f"{device_name}.boardfarm.com"
        self._add_dns_addresses(ipv4_address, ipv6_address)
        self._add_aux_dns_addresses(aux_url)
        self.hosts_v4.update(self.dnsv4)
        self.hosts_v6.update(self.dnsv6)
        self.nslookup = NSLookup(console)

    def _add_dns_addresses(
        self,
        ipv4_address: str | None,
        ipv6_address: str | None,
    ) -> None:
        if ipv4_address is not None:
            self.dnsv4[self.fqdn].append(ipv4_address)
        if ipv6_address is not None:
            self.dnsv6[self.fqdn].append(ipv6_address)

    def _add_aux_dns_addresses(self, aux_url: str | None) -> None:
        if self.auxv4 is not None:
            self.dnsv4[self.fqdn].append(self.auxv4)
            if aux_url is not None:
                self.dnsv4[aux_url].append(self.auxv4)
        if self.auxv6 is not None:
            self.dnsv6[self.fqdn].append(self.auxv6)
            if aux_url is not None:
                self.dnsv6[aux_url].append(self.auxv6)

    def configure_hosts(
        self,
        reachable_ipv4: int,
        unreachable_ipv4: int,
        reachable_ipv6: int,
        unreachable_ipv6: int,
    ) -> None:
        """Create the given number of reachable and unreachable ACS domain IP's.

        :param reachable_ipv4: no.of reachable IPv4 address for acs url
        :type reachable_ipv4: int
        :param unreachable_ipv4: no.of unreachable IPv4 address for acs url
        :type unreachable_ipv4: int
        :param reachable_ipv6: no.of reachable IPv6 address for acs url
        :type reachable_ipv6: int
        :param unreachable_ipv6: no.of unreachable IPv6 address for acs url
        :type unreachable_ipv6: int
        """
        val_v4 = self.hosts_v4[self.fqdn][:reachable_ipv4]
        val_v6 = self.hosts_v6[self.fqdn][:reachable_ipv6]
        self.hosts_v4[self.fqdn] = val_v4
        self.hosts_v6[self.fqdn] = val_v6
        for val in range(unreachable_ipv4):
            ipv4 = self.auxv4 + (val + 1)
            self.hosts_v4[self.fqdn].append(str(ipv4))
        for val in range(unreachable_ipv6):
            ipv6 = self.auxv6 + (val + 1)
            self.hosts_v6[self.fqdn].append(str(ipv6))


class HTTPResult:  # pylint: disable=too-few-public-methods
    """Class to save the object of parsed HTTP response."""

    def __init__(self, response: str) -> None:
        """Parse the response and save it as an instance.

        :param response: response from HTTP request
        :type response: str
        """
        self.response = response
        self.raw, self.code, self.beautified_text = self._parse_response(response)

    @staticmethod
    def _parse_response(response: str) -> tuple[str, str, str]:
        if "Connection refused" in response or "Connection timed out" in response:
            msg = f"Curl Failure due to the following reason {response}"
            raise UseCaseFailure(msg)
        raw_search_output = re.findall(
            r"\<[\!DOC|head][\S\n ].+body\>",
            response,
            re.DOTALL,
        )
        raw = raw_search_output[0] if raw_search_output else ""

        code_search_output = re.findall(r"< HTTP\/.*\s(\d+)", response)
        code = code_search_output[0] if code_search_output else ""

        beautified_text = ""
        if raw:
            soup = BeautifulSoup(raw, "html.parser")
            beautified_text = str(soup.prettify())

        return raw, code, beautified_text


def http_get(
    console: _LinuxConsole, url: str, timeout: int = 20, options: str = ""
) -> HTTPResult:
    """Peform http get (via curl) and return parsed result.

    :param console: console or device instance
    :type console: _LinuxConsole
    :param url: url to get the response
    :type url: str
    :param timeout: connection timeout for the curl command in seconds
    :type timeout: int
    :param options: additional curl command line options, defaults to ""
    :type options: str
    :return: parsed http response
    :rtype: HTTPResult
    """
    return HTTPResult(
        console.execute_command(f"curl -v {options} --connect-timeout {timeout} {url}"),
    )


def dns_lookup(
    console: _LinuxConsole, domain_name: str, record_type: str, opts: str = ""
) -> list[dict[str, Any]]:
    """Perform ``dig`` command in the devices to resolve DNS.

    :param console: console or device instance
    :type console: _LinuxConsole
    :param domain_name: domain name which needs lookup
    :type domain_name: str
    :param record_type: AAAA for ipv6 else A
    :type record_type: str
    :param opts: options to be provided to dig command, defaults to ""
    :type opts: str
    :return: parsed dig command ouput
    :rtype: List[Dict[str, Any]]
    """
    return dig.parse(
        console.execute_command(f"dig {opts} {record_type} {domain_name}").split(
            ";", 1
        )[-1]
    )


def is_link_up(
    console: _LinuxConsole,
    interface: str,
    pattern: str = "BROADCAST,MULTICAST,UP",
) -> bool:
    """Check given interface is up or not.

    :param console: console or device instance
    :type console: _LinuxConsole
    :param interface: interface name, defaults to "BROADCAST,MULTICAST,UP"
    :type interface: str
    :param pattern: interface state
    :type pattern: str
    :return: True if the link is up
    :rtype: bool
    """
    return pattern in console.execute_command(f"ip link show {interface}")


def nmap(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_device: LAN | WLAN | WAN,
    destination_device: LAN | WLAN | WAN | CPE,
    ip_type: str,
    port: str | int | None = None,
    protocol: str | None = None,
    max_retries: int | None = None,
    min_rate: int | None = None,
    opts: str | None = None,
    timeout: int = 30,
) -> dict[str, str]:
    """Run an nmap scan from source to destination device.

    :param source_device: device initiating the scan
    :type source_device: LAN | WLAN | WAN
    :param destination_device: device to be scanned
    :type destination_device: LAN | WLAN | WAN | CPE
    :param ip_type: IP version to use in scan, must be "ipv4" or "ipv6"
    :type ip_type: str
    :param port: port or port range to scan, optional
    :type port: str | int | None
    :param protocol: protocol to scan (e.g., tcp, udp), optional
    :type protocol: str | None
    :param max_retries: maximum number of retransmissions, optional
    :type max_retries: int | None
    :param min_rate: minimum number of packets per second to send, optional
    :type min_rate: int | None
    :param opts: additional nmap command-line options, optional
    :type opts: str | None
    :param timeout: timeout value for the scan (in seconds), defaults to 30
    :type timeout: int
    :return: parsed nmap scan result as a dictionary
    :rtype: dict[str, str]
    """
    iface: str = (
        destination_device.sw.erouter_iface
        if isinstance(destination_device, CPE)
        else destination_device.iface_dut
    )
    dest_device: LAN | WLAN | WAN | CPESW = (
        destination_device.sw
        if isinstance(destination_device, CPE)
        else destination_device
    )
    ipaddr: str = (
        dest_device.get_interface_ipv4addr(iface)
        if ip_type == "ipv4"
        else f"-6 {dest_device.get_interface_ipv6addr(iface)}"
    )
    return source_device.nmap(
        ipaddr, ip_type, port, protocol, max_retries, min_rate, opts, timeout=timeout
    )
