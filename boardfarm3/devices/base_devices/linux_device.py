"""Boardfarm Linux device module."""

import re
from argparse import Namespace
from collections.abc import Generator
from contextlib import contextmanager, suppress
from ipaddress import IPv4Address, IPv4Interface, IPv6Address, IPv6Interface
from typing import Any, Optional, Union

import jc.parsers.ping
import pexpect

from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.exceptions import (
    BoardfarmException,
    ConfigurationFailure,
    SCPConnectionError,
)
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
from boardfarm3.lib.connection_factory import connection_factory
from boardfarm3.lib.connections.local_cmd import LocalCmd
from boardfarm3.lib.networking import (
    HTTPResult,
    IptablesFirewall,
    dns_lookup,
    http_get,
    is_link_up,
)
from boardfarm3.lib.regexlib import AllValidIpv6AddressesRegex, LinuxMacFormat


# pylint: disable-next=too-many-instance-attributes,too-many-public-methods
class LinuxDevice(BoardfarmDevice):
    """Boardfarm Linux device."""

    eth_interface = "eth1"
    _internet_access_cmd = ""

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:  # noqa: C901
        """Initialize linux device.

        :param config: device configuration
        :param cmdline_args: command line arguments
        """
        super().__init__(config, cmdline_args)
        self._console: BoardfarmPexpect = None
        self._shell_prompt = ["[\\w-]+@[\\w-]+:[\\w/~]+#"]
        self.firewall = IptablesFirewall(self._console)

        if "options" in self._config:
            options = [x.strip() for x in self._config["options"].split(",")]
            for opt in options:
                if opt.startswith("wan-static-route:"):
                    self.static_route = opt.replace("wan-static-route:", "").replace(
                        "-", " via "
                    )
                # TODO: remove wan-static-route at some point above
                if opt.startswith("static-route:"):
                    self.static_route = opt.replace("static-route:", "").replace(
                        "-", " via "
                    )
                if opt == "wan-dhcp-client":
                    self.wan_dhcp = True
                if opt == "wan-no-eth0":
                    self.wan_no_eth0 = True
                if opt == "wan-no-dhcp-server":
                    self.wan_dhcp_server = False
                if opt == "wan-dhcp-client-v6":
                    self.wan_dhcpv6 = True
                if opt.startswith("mgmt-dns:"):
                    value = str(opt.replace("mgmt-dns:", ""))
                    self.mgmt_dns = IPv4Interface(value).ip
                else:
                    self.mgmt_dns = IPv4Address("8.8.8.8")
                if opt == "dante":
                    self.dante = True

    @property
    def _ipaddr(self) -> str:
        """Management IP address of the device."""  # noqa: D401
        return self._config.get("ipaddr")

    @property
    def _port(self) -> str:
        """Management connection port of the device."""  # noqa: D401
        return self._config.get("port", "22")

    @property
    def _username(self) -> str:
        """Management connection username."""  # noqa: D401
        return self._config.get("username", "root")

    @property
    def _password(self) -> str:
        """IP address of the device."""
        return self._config.get("password", "bigfoot1")

    def _connect(self) -> None:
        """Establish connection to the device via SSH."""
        if self._console is None:
            self._console = connection_factory(
                self._config.get("connection_type"),
                f"{self.device_name}.console",
                username=self._username,
                password=self._password,
                ip_addr=self._ipaddr,
                port=self._port,
                shell_prompt=self._shell_prompt,
            )
            # This fixes the terminal prompt on long lines
            self._console.execute_command(
                "stty columns 400; export TERM=xterm",
            )

    def _disconnect(self) -> None:
        """Disconnect SSH connection to the server."""
        if self._console is not None:
            self._console.close()
            self._console = None

    def get_interactive_consoles(self) -> dict[str, BoardfarmPexpect]:
        """Get interactive consoles of the device.

        :returns: interactive consoles of the device
        """
        interactive_consoles = {}
        if self._console is not None:
            interactive_consoles["console"] = self._console
        return interactive_consoles

    def _get_nw_interface_ip_address(
        self, interface_name: str, is_ipv6: bool
    ) -> list[str]:
        """Get network interface ip address.

        :param interface_name: interface name
        :param is_ipv6: is ipv6 address
        :returns: IP address list
        """
        prefix = "inet6" if is_ipv6 else "inet"
        ip_regex = prefix + r"\s(?:addr:)?\s*([^\s/]+)"
        output = self._console.execute_command(f"ifconfig {interface_name}")
        return re.findall(ip_regex, output)

    def _get_nw_interface_ipv4_address(self, network_interface: str) -> str:
        """Get IPv4 adddress of the given network interface.

        :param network_interface: network interface name
        :returns: IPv4 address of the given interface, None if not available
        """
        return (
            ips[0]
            if (ips := self._get_nw_interface_ip_address(network_interface, False))
            else None
        )

    def _get_nw_interface_ipv6_address(
        self, network_interface: str, address_type: str = "global"
    ) -> str:
        """Get IPv6 address of the given network interface.

        :param network_interface: network interface name
        :param address_type: ipv6 address type. defaults to "global".
        :returns: IPv6 address of the given interface, None if not available
        """
        address_type = address_type.replace("-", "_")
        ip_addresses = self._get_nw_interface_ip_address(network_interface, True)
        return next(
            (
                ip_addr
                for ip_addr in ip_addresses
                if getattr(IPv6Interface(ip_addr), f"is_{address_type}")
            ),
            None,
        )

    def get_eth_interface_ipv4_address(self) -> str:
        """Get eth interface ipv4 address.

        :returns: IPv4 address of eth interface
        """
        return self._get_nw_interface_ipv4_address(self.eth_interface)

    def get_eth_interface_ipv6_address(self, address_type: str = "global") -> str:
        """Get IPv6 address of eth interface.

        :param address_type: ipv6 address type. defaults to "global".
        :returns: IPv6 address of eth interface
        """
        return self._get_nw_interface_ipv6_address(self.eth_interface, address_type)

    def scp_local_file_to_device(self, local_path: str, destination_path: str) -> None:
        """Copy a local file to a server using SCP.

        :param source: local file path
        :param destination: destination path
        :raises SCPConnectionError: when failed to perform SCP
        :raises EnvConfigError: when given password is None
        :raises SCPConnectionError: when SCP command return non-zero exit code
        """
        destination_path = (
            f"{self._username}@{self._config.get('ipaddr')}:{destination_path}"
        )
        args = [
            f"-P {self._config.get('port', '22')}",
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            "-o ServerAliveInterval=60",
            "-o ServerAliveCountMax=5",
            local_path,
            destination_path,
        ]
        session = LocalCmd(f"{self.device_name}.scp", "scp", args)
        session.setwinsize(24, 80)
        match_index = session.expect(
            [" password:", "\\d+%", pexpect.TIMEOUT, pexpect.EOF], timeout=20
        )
        if match_index in (2, 3):
            raise SCPConnectionError(
                f"Failed to perform SCP from {local_path} to {destination_path}"
            )
        if match_index == 0:
            session.sendline(self._password)
        session.expect(pexpect.EOF, timeout=90)
        if session.wait() != 0:
            raise SCPConnectionError(
                f"Failed to SCP file from {local_path} to {destination_path}"
            )

    def download_file_from_uri(self, file_uri: str, destination_dir: str) -> str:
        """Download(wget) file from given URI.

        :param file_uri: file uri location
        :param destination_dir: destination directory
        :returns: downloaded file name
        :raises ConfigurationFailure: when file download failed from given URI
        """
        file_name = file_uri.split("/")[-1]
        file_path = f"{destination_dir}/{file_name}"
        if " saved [" not in self._console.execute_command(
            f"{self._internet_access_cmd} wget '{file_uri}' -O {file_path}"
        ):
            raise ConfigurationFailure(f"Failed to download file from {file_uri}")
        return file_name

    def curl(
        self,
        url: Union[str, IPv4Address],
        protocol: str,
        port: Optional[Union[str, int]] = None,
        options: str = "",
    ) -> bool:
        """Perform curl action to web service.

        :param url: address of the server
        :param protocol: Web Protocol (http or https)
        :param port: port number of server
        :param options: Additional curl options
        :return: True if connection is successful, False otherwise
        """
        if not isinstance(url, str):
            url = str(url)
        if port:
            if re.search(AllValidIpv6AddressesRegex, url) and "[" not in url:
                url = f"[{url}]"
            web_addr = f"{protocol}://{url}:{str(port)}"
        else:
            web_addr = f"{protocol}://{url}"
        command = f"curl -v {options} {web_addr}"
        self._console.before = None
        self._console.sendline(command)
        index = self._console.expect(
            [
                "Connected to",
                "DOCTYPE html PUBLIC",
                "doctype html",
                "Connection timed out",
                "Failed to connect to",
                "Couldn't connect to server",
            ],
            timeout=100,
        )
        try:
            self._console.expect(self._shell_prompt)
        except pexpect.exceptions.TIMEOUT:
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)
        return index in [0, 1, 2]

    def set_link_state(self, interface: str, state: str) -> None:
        """Set interface state.

        :param interface: interface name
        :param state: interface state
        """
        self._console.sudo_sendline(f"ip link set {interface} {state}")
        self._console.expect(self._shell_prompt)

    def is_link_up(
        self, interface: str, pattern: str = "BROADCAST,MULTICAST,UP"
    ) -> bool:
        """Check given interface is up or not.

        :param interface: interface name, defaults to "BROADCAST,MULTICAST,UP"
        :type interface: str
        :param pattern: interface state
        :type pattern: str, optional
        :return: True if the link is up
        :rtype: bool
        """
        return is_link_up(self._console, interface, pattern)

    def get_interface_ipv4addr(self, interface: str) -> str:
        """Get ipv4 address of interface."""
        return self._get_nw_interface_ipv4_address(interface)

    def get_interface_ipv6addr(self, interface: str) -> str:
        """Get ipv6 address of the interface.

        :param interface: interface name to get the link local
        :return: Global ipv6 address of the interface
        :raises BoardfarmException: in case ipv6 can not be found
        """
        return self._get_nw_interface_ipv6_address(
            network_interface=interface, address_type="global"
        )

    def get_interface_link_local_ipv6addr(self, interface: str) -> str:
        """Get ipv6 link local address of the interface.

        :param interface: interface name
        :return: Link local ipv6 address of the interface
        :raises BoardfarmException: in case ipv6 can not be found
        """
        return self._get_nw_interface_ipv6_address(
            network_interface=interface, address_type="link-local"
        )

    def get_interface_macaddr(self, interface: str) -> str:
        """Get the interface MAC address.

        :param interface: interface name
        :return: MAC address of the interface
        """
        self._console.sendline(f"cat /sys/class/net/{interface}/address | \\")
        self._console.sendline("awk '{print \"bft_macaddr : \"$1}'")
        self._console.expect(f"bft_macaddr : {LinuxMacFormat}")
        macaddr = self._console.match.group(1)
        self._console.expect(self._shell_prompt)
        return macaddr

    def ping(
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: Optional[str] = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> Union[bool, dict[str, Any]]:
        """Ping remote host.

        Return True if ping has 0% loss
        or parsed output in JSON if json_output=True flag is provided.

        :param ping_ip: ping ip
        :param ping_count: number of ping, defaults to 4
        :param ping_interface: ping via interface, defaults to None
        :param options: extra ping options, defaults to ""
        :param timeout: timeout, defaults to 50
        :param json_output: return ping output in dictionary format, defaults to False
        :return: ping output as str or dict
        """
        cmd = f"ping -c {ping_count} {ping_ip}"

        if ping_interface:
            cmd += f" -I {ping_interface}"

        cmd += f" {options}"
        self._console.sendline(cmd)
        self._console.expect(self._shell_prompt, timeout=timeout)

        if json_output:
            return jc.parsers.ping.parse(self._console.before)

        match = re.search(
            f"{ping_count} packets transmitted, {ping_count} "
            "[packets ]*received, 0%% packet loss",
            self._console.before,
        )
        return bool(match)

    def traceroute(
        self,
        host_ip: Union[str, IPv4Address, IPv6Address],
        version: str = "",
        options: str = "",
        timeout: int = 60,
    ) -> Optional[str]:
        """Get traceroute output.

        :param host_ip: destination ip
        :param version: empty or 6
        :param options: traceroute command options
        :param timeout: command timeout
        :return: traceroute output if command finished before timeout, None otherwise
        """
        try:
            self._console.sendline(f"traceroute{version} {options} {host_ip}")
            self._console.expect_exact(f"traceroute{version} {options} {host_ip}")
            self._console.expect(self._shell_prompt, timeout=timeout)
            return self._console.before
        except pexpect.TIMEOUT:
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)
            return None

    @contextmanager
    def tcpdump_capture(
        self,
        fname: str,
        interface: str = "any",
        additional_args: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Capture packets from specified interface.

        Packet capture using tcpdump utility at a specified interface.

        :param fname: name of the file where packet captures will be stored
        :param interface: name of the interface, defaults to "all"
        :param additional_args: arguments to tcpdump command, defaults to None
        :return: process id of tcpdump process
        """
        process_id: str = ""
        command_str = f"tcpdump -U -i {interface} -n -w {fname} "
        if additional_args:
            command_str += additional_args

        try:
            self._console.sendline(f"sudo {command_str} &")
            self._console.expect_exact(f"tcpdump: listening on {interface}")
            process_id = re.search(r"(\[\d{1,10}\]\s(\d+))", self._console.before)[2]

            yield process_id

        finally:
            # This should always be executed, might kill other tcpdumps[need to agree]
            if process_id:
                self._console.sudo_sendline(f"kill {process_id}")
                self._console.expect(self._shell_prompt)
                for _ in range(3):
                    with suppress(pexpect.TIMEOUT):
                        self._console.sudo_sendline("sync")
                        self._console.expect(self._shell_prompt)
                        if "Done" in self._console.before:
                            break

    def tcpdump_read_pcap(
        self,
        fname: str,
        additional_args: Optional[str] = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file.

        :param fname: name of file to read from
        :param additional_args: filter to apply on packet display, defaults to None
        :param timeout: time for tcpdump read command to complete, defaults to 30
        :param rm_pcap: if True remove packet capture file after read, defaults to False
        :return: console output from the command execution
        """
        output = self._run_command_with_args(
            "sudo tcpdump -n -r", fname, additional_args, timeout
        )

        if "No such file or directory" in output:
            raise FileNotFoundError(
                f"pcap file {fname} not found on {self.device_name} device"
            )
        if "syntax error in filter expression" in output:
            raise BoardfarmException(
                "Invalid filters for tcpdump read, "
                f"review additional_args={additional_args}"
            )
        if rm_pcap:
            self._console.sendline(f"sudo rm {fname}")
            self._console.expect(self._shell_prompt)
        return output

    def tshark_read_pcap(
        self,
        fname: str,
        additional_args: Optional[str] = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file.

        :param fname: name of the file in which captures are saved
        :param additional_args: additional arguments for tshark command
        :param timeout: timeout for tshark command to be executed, defaults to 30
        :param rm_pcap: If True remove the packet capture file after reading it
        :return: return tshark read command console output
        """
        output = self._run_command_with_args(
            "sudo tshark -r", fname, additional_args, timeout
        )

        if f'The file "{fname}" doesn\'t exist' in output:
            raise FileNotFoundError(
                f"pcap file not found {fname} on device {self.device_name}"
            )
        if "was unexpected in this context" in output:
            raise BoardfarmException(
                "Invalid filters for tshark read, "
                f"review additional_args={additional_args}"
            )
        if rm_pcap:
            self._console.sendline(f"sudo rm {fname}")
            self._console.expect(self._shell_prompt)
        return output

    def _run_command_with_args(
        self, command: str, fname: str, additional_args: Optional[str], timeout: int
    ) -> str:
        """Run command with given arguments and return the output."""
        read_command = f"{command} {fname} "
        if additional_args:
            read_command += additional_args
        self._console.sendline(read_command)
        self._console.expect(self._shell_prompt, timeout=timeout)
        return self._console.before

    def release_dhcp(self, interface: str) -> None:
        """Release ipv4 of the interface.

        :param interface: release an ipv4 on this iface
        """
        self._console.sudo_sendline(f"dhclient -r {interface!s}")
        self._console.expect(self._shell_prompt)

    def renew_dhcp(self, interface: str) -> None:
        """Renew ipv4 of the interface.

        :param interface: renew an ipv4 on this iface
        """
        self._console.sudo_sendline(f"dhclient -v {interface!s}")
        if (
            self._console.expect([pexpect.TIMEOUT] + self._shell_prompt, timeout=30)
            == 0
        ):
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)

    def release_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Release ipv6 of the interface.

        :param interface: release an ipv6 on this iface
        :param stateless: add -S to release command if True, -6 otherwise
        """
        mode = "-S" if stateless else "-6"
        self._console.sudo_sendline(f"dhclient {mode} -r {interface!s}")
        self._console.expect(self._shell_prompt)

    def renew_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Renew ipv6 of the interface.

        :param interface: renew an ipv6 on this iface
        :param stateless: add -S to release command if True, -6 otherwise
        """
        mode = "-S" if stateless else "-6"
        self._console.sudo_sendline(f"dhclient {mode} -v {interface!s}")
        if (
            self._console.expect([pexpect.TIMEOUT] + self._shell_prompt, timeout=15)
            == 0
        ):
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)

    def start_http_service(self, port: str, ip_version: str) -> str:
        """Start HTTP service on given port number.

        :param port: port number
        :param ip_version: ip version, 4 - IPv4, 6 - IPv6
        :return: pid number of the http service
        """
        cmd_output = self._console.execute_command(
            f"webfsd -F -p {port} -{ip_version} &"
        )
        if "Address already in use" in cmd_output:
            raise BoardfarmException(f"Failed to start http service on port {port}.")
        return re.search(r"(\[\d{1,}\]\s(\d+))", cmd_output)[2]

    def stop_http_service(self, port: str) -> None:
        """Stop http service running on given port.

        :param port: port number
        """
        ps_cmd = f"""ps auxwww | grep "webfsd -F -p {port}" | grep -v grep"""
        if not self._console.execute_command(ps_cmd).splitlines():
            return
        self._console.execute_command(
            ps_cmd + " | awk -F ' ' '{print $2}' | xargs kill -9 "
        )
        if self._console.execute_command(ps_cmd).splitlines():
            raise BoardfarmException(
                f"Failed to kill webfsd process running on port {port}"
            )

    def http_get(self, url: str, timeout: int) -> HTTPResult:
        """Peform http get (via curl) and return parsed result.

        :param url: url to get the response
        :type url: str
        :param timeout: connection timeout for the curl command in seconds
        :type timeout: int
        :return: parsed http response
        :rtype: HTTPResult
        """
        return http_get(self._console, url, timeout)

    def dns_lookup(self, domain_name: str) -> list[dict[str, Any]]:
        """Run ``dig`` command and return the parsed result.

        :param domain_name: domain name which needs lookup
        :type domain_name: str
        :return: parsed dig command output
        :rtype: List[Dict[str, Any]]
        """
        return dns_lookup(self._console, domain_name)
