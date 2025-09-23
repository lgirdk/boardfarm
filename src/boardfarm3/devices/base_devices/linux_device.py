"""Boardfarm Linux device module."""

# pylint: disable=too-many-lines
# pylint: disable=too-many-nested-blocks

from __future__ import annotations

import logging
import re
import tempfile
from contextlib import contextmanager, suppress
from functools import cached_property
from ipaddress import IPv4Address, IPv4Interface, IPv6Address, IPv6Interface
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Any

import jc.parsers.ping
import pexpect
import xmltodict

from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.exceptions import (
    BoardfarmException,
    CodeError,
    ConfigurationFailure,
    NotSupportedError,
    SCPConnectionError,
)
from boardfarm3.lib.connection_factory import connection_factory
from boardfarm3.lib.connections.local_cmd import LocalCmd
from boardfarm3.lib.network_utils import NetworkUtility
from boardfarm3.lib.networking import HTTPResult, dns_lookup, http_get, is_link_up
from boardfarm3.lib.networking import start_tcpdump as start_dump
from boardfarm3.lib.networking import stop_tcpdump as stop_dump
from boardfarm3.lib.regexlib import AllValidIpv6AddressesRegex, LinuxMacFormat
from boardfarm3.lib.shell_prompt import DEFAULT_BASH_SHELL_PROMPT_PATTERN

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Generator

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.multicast import MulticastGroupRecord

__LOGGER = logging.getLogger(__name__)


# pylint: disable-next=too-many-instance-attributes,too-many-public-methods
class LinuxDevice(BoardfarmDevice):
    """Boardfarm Linux device."""

    eth_interface = "eth1"
    _internet_access_cmd = ""

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize linux device.

        :param config: device configuration
        :type config: dict
        :param cmdline_args: command line arguments
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)
        self._console: BoardfarmPexpect = None
        self._shell_prompt = [DEFAULT_BASH_SHELL_PROMPT_PATTERN]
        self._static_route = ""
        if "options" in self._config:
            options = [x.strip() for x in self._config["options"].split(",")]
            for opt in options:
                if opt.startswith("static-route:"):
                    self._static_route = opt.replace("static-route:", "").replace(
                        "-",
                        " via ",
                    )
                if opt.startswith("mgmt-dns:"):
                    value = str(opt.replace("mgmt-dns:", ""))
                    self.mgmt_dns = IPv4Interface(value).ip
                else:
                    self.mgmt_dns = IPv4Address("8.8.8.8")
                if opt == "dante":
                    self.dante = True
        self._nw_utility: NetworkUtility = None

    def _parse_device_suboptions(self) -> dict[str, str]:
        """Parse the sub-options provided in device config.

        :return: parsed sub-options
        :rtype: dict[str, str]
        """
        parsed_options: dict[str, str] = {}

        if "options" not in self._config:
            return parsed_options

        options = [x.strip() for x in self._config["options"].split(",")]
        for opt in options:
            split = opt.strip().split(":", 1)
            if len(split) == 1:
                parsed_options[split[0]] = ""
            else:
                parsed_options[split[0].strip()] = split[1].strip()

        return parsed_options

    async def _setup_static_routes_async(self) -> None:
        """Set up static routes for the device.

        :raises ValueError: if the syntax is incorrect in inventory
        """
        options = self._parse_device_suboptions()
        for option, opt_val in options.items():
            if option == "static-route":
                for route_entry in opt_val.split(";"):
                    try:
                        destination, gateway = map(str.strip, route_entry.split("-"))
                        await self._console.execute_command_async(
                            f"ip route del {destination}"
                        )
                        await self._console.execute_command_async(
                            f"ip route add {destination} via {gateway}"
                        )
                    except pexpect.TIMEOUT:  # noqa: PERF203
                        __LOGGER.exception("Failed to set up route %s", route_entry)
                    except TypeError as exc:
                        msg = f"Validate the syntax of static-route for {opt_val}."
                        raise ValueError(msg) from exc

    def _setup_static_routes(self) -> None:
        """Set up static routes for the device.

        :raises ValueError: if the syntax is incorrect in inventory
        """
        options = self._parse_device_suboptions()
        for option, opt_val in options.items():
            if option == "static-route":
                for route_entry in opt_val.split(";"):
                    try:
                        destination, gateway = map(str.strip, route_entry.split("-"))
                        self._console.execute_command(f"ip route del {destination}")
                        self._console.execute_command(
                            f"ip route add {destination} via {gateway}"
                        )
                    except pexpect.TIMEOUT:  # noqa: PERF203
                        __LOGGER.exception("Failed to set up route %s", route_entry)
                    except TypeError as exc:
                        msg = f"Validate the syntax of static-route for {opt_val}."
                        raise ValueError(msg) from exc

    @property
    def _ipaddr(self) -> str:
        """Management IP address of the device.

        :return: ipaddress of the device
        :rtype: str
        """
        return self._config.get("ipaddr")

    @property
    def _port(self) -> str:
        """Management connection port of the device.

        :return: management connection port of the device
        :rtype: str
        """
        return self._config.get("port", "22")

    @property
    def _username(self) -> str:
        """Management connection username.

        :return: management iface username
        :rtype: str
        """
        return self._config.get("username", "root")

    @property
    def _password(self) -> str:
        """Management connection password.

        :return: management iface password
        :rtype: str
        """
        return self._config.get("password", "bigfoot1")

    @cached_property
    def ipv4_addr(self) -> str:
        """Return the IPv4 address on IFACE facing DUT.

        :return: IPv4 address in string format.
        :rtype: str
        """
        return self._get_nw_interface_ipv4_address(self.eth_interface)

    @cached_property
    def ipv6_addr(self) -> str:
        """Return the IPv6 address on IFACE facing DUT.

        :return: IPv6 address in string format.
        :rtype: str
        """
        return self._get_nw_interface_ipv6_address(
            self.eth_interface, address_type="global"
        )

    def clear_cache(self) -> None:
        """To clear all the cached properties."""
        self.__dict__.pop("ipv4_addr", None)
        self.__dict__.pop("ipv6_addr", None)

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
                save_console_logs=self._cmdline_args.save_console_logs,
            )
            self._console.login_to_server(password=self._password)
            # This fixes the terminal prompt on long lines
            self._console.execute_command(
                "stty columns 400; export TERM=xterm",
            )

    async def _connect_async(self) -> None:
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
                save_console_logs=self._cmdline_args.save_console_logs,
            )
            await self._console.login_to_server_async(password=self._password)
            # This fixes the terminal prompt on long lines
            await self._console.execute_command_async(
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
        self,
        interface_name: str,
        is_ipv6: bool,
    ) -> list[str]:
        """Get network interface ip address.

        :param interface_name: interface name
        :param is_ipv6: is ipv6 address
        :returns: IP address list
        :raises NotSupportedError: when property gets called and console obj isn't created
        """
        if not self._console:
            raise NotSupportedError
        prefix = "inet6" if is_ipv6 else "inet"
        ip_regex = prefix + r"\s(?:addr:)?\s*([^\s/]+)"
        output = self._console.execute_command(f"ifconfig {interface_name}")
        return re.findall(ip_regex, output)

    async def _get_nw_interface_ip_address_async(
        self,
        interface_name: str,
        is_ipv6: bool,
    ) -> list[str]:
        """Get network interface ip address.

        :param interface_name: interface name
        :param is_ipv6: is ipv6 address
        :returns: IP address list
        """
        prefix = "inet6" if is_ipv6 else "inet"
        ip_regex = prefix + r"\s(?:addr:)?\s*([^\s/]+)"
        output = await self._console.execute_command_async(f"ifconfig {interface_name}")
        return re.findall(ip_regex, output)

    def _get_nw_interface_ipv4_address(self, network_interface: str) -> str:
        """Get IPv4 adddress of the given network interface.

        :param network_interface: network interface name
        :returns: IPv4 address of the given interface, None if not available
        """
        return (
            ips[0]
            if (ips := self._get_nw_interface_ip_address(network_interface, False))
            else ""
        )

    async def _get_nw_interface_ipv4_address_async(self, network_interface: str) -> str:
        """Get IPv4 adddress of the given network interface.

        :param network_interface: network interface name
        :returns: IPv4 address of the given interface, None if not available
        """
        return (
            ips[0]
            if (
                ips := await self._get_nw_interface_ip_address_async(
                    network_interface,
                    False,
                )
            )
            else ""
        )

    def _get_nw_interface_ipv6_address(
        self,
        network_interface: str,
        address_type: str = "global",
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
            "",
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

    def get_interface_mask(self, interface: str) -> str:
        """Get the subnet mask of the interface.

        :param interface: name of the interface
        :type interface: str
        :return: subnet mask of interface
        :rtype: str
        """
        return re.search(
            r"(?:net)?[Mm]ask\s+(\S+)",
            self._console.execute_command(f"ifconfig {interface}"),
        ).group(1)

    def scp_device_file_to_local(self, local_path: str, source_path: str) -> None:
        """Copy a local file from a server using SCP.

        :param local_path: local file path
        :param source_path: source path
        """
        source_path = f"{self._username}@{self._config.get('ipaddr')}:{source_path}"
        self._scp_local_files(source=source_path, destination=local_path)

    def scp_local_file_to_device(self, local_path: str, destination_path: str) -> None:
        """Copy a local file to a server using SCP.

        :param local_path: local file path
        :param destination_path: destination path
        """
        destination_path = (
            f"{self._username}@{self._config.get('ipaddr')}:{destination_path}"
        )
        self._scp_local_files(source=local_path, destination=destination_path)

    def _scp_local_files(self, source: str, destination: str) -> None:
        """Perform file copy on local console using SCP.

        :param source: source file path
        :param destination: destination file path
        :raises SCPConnectionError: when SCP command return non-zero exit code
        """
        args = [
            f"-P {self._config.get('port', '22')}",
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            "-o ServerAliveInterval=60",
            "-o ServerAliveCountMax=5",
            source,
            destination,
        ]
        session = LocalCmd(
            f"{self.device_name}.scp",
            "scp",
            save_console_logs="",
            args=args,
            # TODO: why do we need to pass shell prompt?
            shell_prompt=self._shell_prompt,
        )
        session.setwinsize(24, 80)
        match_index = session.expect(
            [" password:", "\\d+%", pexpect.TIMEOUT, pexpect.EOF],
            timeout=20,
        )
        if match_index in (2, 3):
            msg = f"Failed to perform SCP from {source} to {destination}"
            raise SCPConnectionError(
                msg,
            )
        if match_index == 0:
            session.sendline(self._password)
        session.expect(pexpect.EOF, timeout=90)
        if session.wait() != 0:
            msg = f"Failed to SCP file from {source} to {destination}"
            raise SCPConnectionError(
                msg,
            )

    def download_file_from_uri(
        self,
        file_uri: str,
        destination_dir: str,
        internet_access_cmd: str = "",
    ) -> str:
        """Download(wget) file from given URI.

        :param file_uri: file uri location
        :param destination_dir: destination directory
        :param internet_access_cmd: cmd to access internet
        :returns: downloaded file name
        :raises ConfigurationFailure: when file download failed from given URI
        """
        if not internet_access_cmd:
            internet_access_cmd = self._internet_access_cmd
        file_name = file_uri.split("/")[-1]
        file_path = f"{destination_dir}/{file_name}"
        if " saved [" not in self._console.execute_command(
            f"{internet_access_cmd} wget {file_uri!r} -O {file_path}",
        ):
            msg = f"Failed to download file from {file_uri}"
            raise ConfigurationFailure(msg)
        return file_name

    def curl(
        self,
        url: str | IPv4Address,
        protocol: str,
        port: str | int | None = None,
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
            web_addr = f"{protocol}://{url}:{port!s}"
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
        self,
        interface: str,
        pattern: str = "BROADCAST,MULTICAST,UP",
    ) -> bool:
        """Check given interface is up or not.

        :param interface: interface name, defaults to "BROADCAST,MULTICAST,UP"
        :type interface: str
        :param pattern: interface state
        :type pattern: str
        :return: True if the link is up
        :rtype: bool
        """
        return is_link_up(self._console, interface, pattern)

    def get_interface_ipv4addr(self, interface: str) -> str:
        """Get ipv4 address of interface.

        :param interface: interface name
        :type interface: str
        :return: Global ipv4 address of the interface
        :rtype: str
        """
        return self._get_nw_interface_ipv4_address(interface)

    def get_interface_ipv6addr(self, interface: str) -> str:
        """Get ipv6 address of the interface.

        :param interface: interface name to get the link local
        :type interface: str
        :return: Global ipv6 address of the interface
        :rtype: str
        """
        return self._get_nw_interface_ipv6_address(
            network_interface=interface,
            address_type="global",
        )

    def get_interface_link_local_ipv6addr(self, interface: str) -> str:
        """Get ipv6 link local address of the interface.

        :param interface: interface name
        :return: Link local ipv6 address of the interface
        """
        return self._get_nw_interface_ipv6_address(
            network_interface=interface,
            address_type="link-local",
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

    def ping(  # noqa: PLR0913
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: str | None = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> bool | dict[str, Any]:
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
            # Remove trailing stray characters observed in certain device consoles
            clean_console_output = self._console.before.replace(
                f"pipe {ping_count}\r\n",
                "",
            )
            return jc.parsers.ping.parse(clean_console_output)

        match = re.search(
            (
                f"{ping_count} packets transmitted, {ping_count} "
                "[packets ]*received, 0% packet loss"
            ),
            self._console.before,
        )
        return bool(match)

    def traceroute(
        self,
        host_ip: str | IPv4Address | IPv6Address,
        version: str = "",
        options: str = "",
        timeout: int = 60,
    ) -> str | None:
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
            # recommended refactoring for TRY300 would work if output type was
            # not mixed
            return self._console.before  # noqa: TRY300
        except pexpect.TIMEOUT:
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)
            return None

    @contextmanager
    def tcpdump_capture(
        self,
        fname: str,
        interface: str = "any",
        additional_args: str | None = None,
    ) -> Generator[str]:
        """Capture packets from specified interface.

        Packet capture using tcpdump utility at a specified interface.

        :param fname: name of the file where packet captures will be stored
        :param interface: name of the interface, defaults to "all"
        :param additional_args: arguments to tcpdump command, defaults to None
        :yield: process id of tcpdump process
        """
        process_id: str = ""
        command_str = f"tcpdump -U -i {interface} -n -w {fname} "
        if additional_args:
            command_str += additional_args

        try:
            self._console.sudo_sendline(f"{command_str} &")
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
        additional_args: str | None = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file.

        :param fname: name of file to read from
        :param additional_args: filter to apply on packet display, defaults to None
        :param timeout: time for tcpdump read command to complete, defaults to 30
        :param rm_pcap: if True remove packet capture file after read, defaults to False
        :return: console output from the command execution
        :raises  FileNotFoundError: when file is not found
        :raises BoardfarmException: when invalid filters are added
        """
        output = self._run_command_with_args(
            "tcpdump -n -r",
            fname,
            additional_args,
            timeout,
        )

        if "No such file or directory" in output:
            msg = f"pcap file {fname} not found on {self.device_name} device"
            raise FileNotFoundError(
                msg,
            )
        if "syntax error in filter expression" in output:
            msg = (
                "Invalid filters for tcpdump read, review "
                f"additional_args={additional_args}"
            )
            raise BoardfarmException(
                msg,
            )
        if rm_pcap:
            self._console.sudo_sendline(f"rm {fname}")
            self._console.expect(self._shell_prompt)
        return output

    def start_tcpdump(
        self,
        interface: str,
        port: str | None,
        output_file: str = "pkt_capture.pcap",
        filters: dict | None = None,
        additional_filters: str | None = "",
    ) -> str:
        """Start tcpdump capture on given interface.

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
        :return: console ouput and tcpdump process id
        :rtype: str
        """
        return start_dump(
            console=self._console,
            interface=interface,
            output_file=output_file,
            filters=filters,
            port=port,
            additional_filters=additional_filters,
        )

    def stop_tcpdump(self, process_id: str) -> None:
        """Stop tcpdump capture.

        :param process_id: tcpdump process id
        :type process_id: str
        """
        stop_dump(self._console, process_id=process_id)

    def tshark_read_pcap(
        self,
        fname: str,
        additional_args: str | None = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file.

        :param fname: name of the file in which captures are saved
        :param additional_args: additional arguments for tshark command
        :param timeout: timeout for tshark command to be executed, defaults to 30
        :param rm_pcap: If True remove the packet capture file after reading it
        :return: return tshark read command console output
        :raises  FileNotFoundError: when file is not found
        :raises BoardfarmException: when invalid filters are added
        """
        output = self._run_command_with_args(
            "tshark -r",
            fname,
            additional_args,
            timeout,
        )

        if f'The file "{fname}" doesn\'t exist' in output:
            msg = f"pcap file not found {fname} on device {self.device_name}"
            raise FileNotFoundError(
                msg,
            )
        if "was unexpected in this context" in output:
            msg = (
                "Invalid filters for tshark read, review "
                f"additional_args={additional_args}"
            )
            raise BoardfarmException(
                msg,
            )
        if rm_pcap:
            self._console.sudo_sendline(f"rm {fname}")
            self._console.expect(self._shell_prompt)
        return output

    def _run_command_with_args(
        self,
        command: str,
        fname: str,
        additional_args: str | None,
        timeout: int,
    ) -> str:
        """Run command with given arguments and return the output.

        :param command: command to run
        :param fname: name of the file in which captures are saved
        :param additional_args:  additional arguments to run command
        :param timeout: timout for the command
        :return: return read command console output
        """
        read_command = f"{command} {fname} "
        if additional_args:
            read_command += additional_args
        self._console.sudo_sendline(read_command)
        self._console.expect(self._shell_prompt, timeout=timeout)
        return self._console.before

    def release_dhcp(self, interface: str) -> None:
        """Release ipv4 of the interface.

        :param interface: release an ipv4 on this iface
        """
        self._console.sudo_sendline(f"dhclient -r {interface!s}")
        self._console.expect(self._shell_prompt)

    async def release_dhcp_async(self, interface: str) -> None:
        """Release ipv4 of the interface.

        :param interface: release an ipv4 on this iface
        """
        self._console.sudo_sendline(f"dhclient -r {interface!s}")
        await self._console.expect(self._shell_prompt, async_=True)

    def renew_dhcp(self, interface: str) -> None:
        """Renew ipv4 of the interface.

        :param interface: renew an ipv4 on this iface
        """
        self._console.sudo_sendline(f"dhclient -v {interface!s}")
        if (
            self._console.expect([pexpect.TIMEOUT, *self._shell_prompt], timeout=30)
            == 0
        ):
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)

    async def renew_dhcp_async(self, interface: str) -> None:
        """Renew ipv4 of the interface.

        :param interface: renew an ipv4 on this iface
        """
        self._console.sudo_sendline(f"dhclient -v {interface!s}")
        if (
            await self._console.expect(
                [pexpect.TIMEOUT, *self._shell_prompt],
                timeout=30,
                async_=True,
            )
            == 0
        ):
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt, async_=True)

    def release_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Release ipv6 of the interface.

        :param interface: release an ipv6 on this iface
        :param stateless: add -S to release command if True, -6 otherwise
        """
        mode = "-S" if stateless else "-6"
        self._console.sudo_sendline(f"dhclient {mode} -r {interface!s}")
        self._console.expect(self._shell_prompt)

    async def release_ipv6_async(self, interface: str, stateless: bool = False) -> None:
        """Release ipv6 of the interface.

        :param interface: release an ipv6 on this iface
        :param stateless: add -S to release command if True, -6 otherwise
        """
        mode = "-S" if stateless else "-6"
        self._console.sudo_sendline(f"dhclient {mode} -r {interface!s}")
        await self._console.expect(self._shell_prompt, async_=True)

    def renew_ipv6(self, interface: str, stateless: bool = False) -> None:
        """Renew ipv6 of the interface.

        :param interface: renew an ipv6 on this iface
        :param stateless: add -S to release command if True, -6 otherwise
        """
        mode = "-S" if stateless else "-6"
        self._console.sudo_sendline(f"dhclient {mode} -v {interface!s}")
        if (
            self._console.expect([pexpect.TIMEOUT, *self._shell_prompt], timeout=15)
            == 0
        ):
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)

    async def renew_ipv6_async(self, interface: str, stateless: bool = False) -> None:
        """Renew ipv6 of the interface.

        :param interface: renew an ipv6 on this iface
        :param stateless: add -S to release command if True, -6 otherwise
        """
        mode = "-S" if stateless else "-6"
        self._console.sudo_sendline(f"dhclient {mode} -v {interface!s}")
        if (
            await self._console.expect(
                [pexpect.TIMEOUT, *self._shell_prompt],
                timeout=15,
                async_=True,
            )
            == 0
        ):
            self._console.sendcontrol("c")
            await self._console.expect(self._shell_prompt, async_=True)

    def start_http_service(self, port: str, ip_version: str) -> str:
        """Start HTTP service on given port number.

        :param port: port number
        :param ip_version: ip version, 4 - IPv4, 6 - IPv6
        :return: pid number of the http service
        :raises BoardfarmException: when http service ifails to start
        """
        cmd_output = self._console.execute_command(
            f"webfsd -F -p {port} -{ip_version} &",
        )
        if "Address already in use" in cmd_output:
            msg = f"Failed to start http service on port {port}."
            raise BoardfarmException(msg)
        return re.search(r"(\[\d{1,}\]\s(\d+))", cmd_output)[2]

    def stop_http_service(self, port: str) -> None:
        """Stop http service running on given port.

        :param port: port number
        :raises BoardfarmException: when http service ifails to stop
        """
        ps_cmd = f"""ps auxwww | grep "webfsd -F -p {port}" | grep -v grep"""
        if not self._console.execute_command(ps_cmd).splitlines():
            return
        self._console.execute_command(
            ps_cmd + " | awk -F ' ' '{print $2}' | xargs kill -9 ",
        )
        for _ in range(4):
            if self._console.execute_command(ps_cmd).splitlines():
                sleep(4)
                continue
            return
        msg = f"Failed to kill webfsd process running on port {port}"
        raise BoardfarmException(
            msg,
        )

    def http_get(self, url: str, timeout: int, options: str) -> HTTPResult:
        """Peform http get (via curl) and return parsed result.

        :param url: url to get the response
        :type url: str
        :param timeout: connection timeout for the curl command in seconds
        :type timeout: int
        :param options: additional options for the curl command
        :type options: str
        :return: parsed http response
        :rtype: HTTPResult
        """
        return http_get(self._console, url, timeout, options)

    def dns_lookup(
        self, domain_name: str, record_type: str, opts: str = ""
    ) -> list[dict[str, Any]]:
        """Run ``dig`` command and return the parsed result.

        :param domain_name: domain name which needs lookup
        :type domain_name: str
        :param record_type: AAAA for ipv6 else A
        :type record_type: str
        :param opts: options to be provided to dig command, defaults to ""
        :type opts: str
        :return: parsed dig command output
        :rtype: List[Dict[str, Any]]
        """
        return dns_lookup(self._console, domain_name, record_type, opts)

    def nmap(  # pylint: disable=too-many-arguments  # noqa: PLR0913
        self,
        ipaddr: str,
        ip_type: str,
        port: str | int | None = None,
        protocol: str | None = None,
        max_retries: int | None = None,
        min_rate: int | None = None,
        opts: str | None = None,
        timeout: int = 30,
    ) -> dict:
        """Perform nmap operation on linux device.

        :param ipaddr: ip address on which nmap is performed
        :type ipaddr: str
        :param ip_type: type of ip eg: ipv4/ipv6
        :type ip_type: str
        :param port: destination port on ip, defaults to None
        :type port: Optional[Union[str, int]], optional
        :param protocol: specific protocol to follow eg: tcp(-sT)/udp(-sU),
            defaults to None
        :type protocol: Optional[str], optional
        :param max_retries: number of port scan probe retransmissions, defaults to None
        :type max_retries: Optional[int], optional
        :param min_rate: Send packets no slower than per second, defaults to None
        :type min_rate: Optional[int], optional
        :param opts: other options for a nmap command, defaults to None
        :type opts: Optional[str], optional
        :param timeout: pexpect timeout for the command in seconds, defaults to 30
        :type timeout: int
        :raises BoardfarmException: Raises exception if ip type is invalid
        :return: response of nmap command in xml/dict format
        :rtype: dict
        """
        if ip_type not in ["ipv4", "ipv6"]:
            msg = "Invalid ip type, should be either ipv4 or ipv6"
            raise BoardfarmException(msg)
        retries = f"-max-retries {max_retries}" if max_retries else ""
        rate = f"-min-rate {min_rate}" if min_rate else ""
        port = f"-p {port}" if port else ""
        cmd = (
            f"nmap {protocol or ''} {port} -Pn -r {opts or ''}"
            f" {ipaddr} {retries} {rate} -oX -"
        )
        return xmltodict.parse(self._console.execute_command(cmd, timeout))

    def start_danteproxy(self) -> None:
        """Start the dante server for socks5 proxy connections.

        :raises BoardfarmException: if dante is not in the device options
        """
        if not self.dante:
            msg = (
                f"Cannot start dante on {self.device_name}, "
                "it is not configured in the device options."
            )
            raise BoardfarmException(
                msg,
            )
        to_send = [
            "cat > /etc/danted.conf <<EOF",
            "logoutput: stderr",
            "internal: 0.0.0.0 port = 8080",
            f"external: {self.eth_interface}",
            "clientmethod: none",
            "socksmethod: username none #rfc931",
            "user.privileged: root",
            "user.unprivileged: nobody",
            "user.libwrap: nobody",
            "client pass {",
            "    from: 0.0.0.0/0 to: 0.0.0.0/0",
            "    log: connect disconnect error",
            "}",
            "socks pass {",
            "    from: 0.0.0.0/0 to: 0.0.0.0/0",
            "    log: connect disconnect error",
            "}",
            "EOF",
        ]
        self._console.sendline("\n".join(to_send))
        self._console.expect(self._shell_prompt)
        # NOTE: service danted restart DOES NOT WORK, hence the stop/start!
        self._console.execute_command(
            "service danted stop; sleep 3;service danted start",
        )

    def stop_danteproxy(self) -> None:
        """Stop the Dante proxy."""
        self._console.execute_command("service danted stop")

    async def stop_danteproxy_async(self) -> None:
        """Stop the Dante proxy."""
        self._console.execute_command_async("service danted stop")

    def start_traffic_receiver(
        self,
        traffic_port: int,
        bind_to_ip: str | None = None,
        ip_version: int | None = None,
        udp_only: bool | None = None,
    ) -> tuple[int, str]:
        """Start the server on a linux device to generate traffic using iperf3.

        :param traffic_port: server port to listen on
        :type traffic_port: int
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to None
        :type bind_to_ip: str, optional
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int, optional
        :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2 as iperf3 does not support
            udp only flag for server
        :type udp_only: bool, optional
        :raises CodeError: raises if unable to start server
        :return: the process id(pid) and log file path
        :rtype: tuple[int , str]
        """
        file_path = tempfile.gettempdir()
        log_file_path = f"{file_path}/iperf_server_logs.txt"
        if udp_only:
            version = ""
            self._console.execute_command(
                f"iperf -s -p {traffic_port}"
                f"{f' -B {bind_to_ip}' if bind_to_ip else ''} -u > {log_file_path} 2>&1 &",
            )
        else:
            version = "3"
            self._console.execute_command(
                f"iperf3{f' -{ip_version}' if ip_version else ''} -s -p {traffic_port}"
                f"{f' -B {bind_to_ip}' if bind_to_ip else ''} > {log_file_path} 2>&1 &",
            )
        output = self._console.execute_command(
            f"sleep 2; ps auxwwww|grep iperf{version}|grep -v grep",
        )
        if f"iperf{version}" in output and "Exit 1" not in output:
            out = re.search(f".* -p {traffic_port}.*", output).group()
            return int(out.split()[1]), log_file_path
        msg = "Unable to start iperf server"
        raise CodeError(msg)

    def start_traffic_sender(  # pylint: disable=too-many-arguments , too-many-locals # noqa: PLR0913
        self,
        host: str,
        traffic_port: int,
        bandwidth: int | None = 5,
        bind_to_ip: str | None = None,
        direction: str | None = None,
        ip_version: int | None = None,
        udp_protocol: bool = False,
        time: int = 10,
        client_port: int | None = None,
        udp_only: bool | None = None,
    ) -> tuple[int, str]:
        """Start traffic on a linux client using iperf3.

        :param host: a host to run in client mode
        :type host: str
        :param traffic_port: server port to connect to
        :type traffic_port: int
        :param bandwidth: bandwidth(mbps) at which the traffic
            has to be generated, defaults to None
        :type bandwidth: Optional[int], optional
        :param bind_to_ip: bind to the interface associated with
            the address host, defaults to 5
        :type bind_to_ip: Optional[str], optional
        :param direction: `--reverse` to run in reverse mode
            (server sends, client receives) or `--bidir` to run in
            bidirectional mode, defaults to None
        :type direction: Optional[str], optional
        :param ip_version: 4 or 6 as it uses only IPv4 or IPv6, defaults to None
        :type ip_version: int, optional
        :param udp_protocol: use UDP rather than TCP, defaults to False
        :type udp_protocol: bool
        :param time: time in seconds to transmit for, defaults to 10
        :type time: int
        :param client_port: client port from where the traffic is getting started
        :type client_port: int | None
        :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
        :type udp_only: bool, optional
        :raises CodeError: raises if unable to start server
        :return: the process id(pid) and log file path
        :rtype: tuple[int , str]
        """
        file_path = tempfile.gettempdir()
        log_file_path = f"{file_path}/iperf_client_logs.txt"
        if udp_only:
            version = ""
            self._console.execute_command(
                f"iperf -c {host} "
                f"-p {traffic_port}{f' -B {bind_to_ip}' if bind_to_ip else ''}"
                f" {f' -b {bandwidth}m' if bandwidth else ''} -t {time} {direction or ''}"
                f" -u > {log_file_path}  2>&1  &",
            )
        else:
            version = "3"
            self._console.execute_command(
                f"iperf3{f' -{ip_version}' if ip_version else ''} -c {host} "
                f"-p {traffic_port}{f' -B {bind_to_ip}' if bind_to_ip else ''}"
                f" {f' -b {bandwidth}m' if bandwidth else ''} -t {time} {direction or ''}"
                f" {f' --cport {client_port}' if client_port else ''}"
                f"{' -u' if udp_protocol else ''} > {log_file_path}  2>&1  &",
            )
        output = self._console.execute_command(
            f"sleep 2; ps auxwwww|grep iperf{version}|grep -v grep",
        )
        if f"iperf{version}" in output and "Exit 1" not in output:
            out = re.search(f".* -c {host} -p {traffic_port}.*", output).group()
            return int(out.split()[1]), log_file_path
        msg = "Unable to start iperf client"
        raise CodeError(msg)

    def get_iperf_logs(self, log_file: str) -> str:
        """Read the file output for traffic flow.

        :param log_file: log file path
        :type log_file: str
        :return: traffic flow logs
        :rtype: str
        """
        self.scp_device_file_to_local(
            local_path=log_file,
            source_path=log_file,
        )
        return Path(log_file).read_text(encoding="utf-8")

    def stop_traffic(self, pid: int | None = None) -> bool:
        """Stop the iPerf3 process for a specific PID or killall.

        :param pid: iPerf3 process ID for reciever or sender, defaults to None
        :type pid: int | None = None
        :return: True if process is stopped else False
        :rtype: bool
        """
        iperf = "iperf" if self._console.execute_command("pgrep iperf") else "iperf3"
        if pid:
            self._console.execute_command(f"kill -9 {pid}")
        else:
            self._console.execute_command(f"killall -9 {iperf}")
        output = self._console.execute_command(f"ps auxwwww|grep {iperf}|grep -v grep")
        return str(pid) not in output if pid else f"{iperf}" not in output

    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        """
        self._console.execute_command(f"rm {filename}")

    def get_date(self) -> str | None:
        """Get the system date and time.

        .. code-block:: python

            # example output
            donderdag, mei 23, 2024 14:23:39


        :return: date
        :rtype: str | None
        """
        cpe_date = self._console.execute_command("date '+%A, %B %d, %Y %T'")
        date = re.search(
            r"(\w+,\s\w+\s\d+,\s\d+\s(([0-1]?[0-9])|(2[0-3])):[0-5][0-9]:[0-5][0-9])",
            cpe_date,
        )
        if date is not None:
            return date.group(0)
        return None

    def set_date(self, opt: str, date_string: str) -> bool:
        """Set the device's date and time.

        :param date_string: value to be changed
        :type date_string: str
        :param opt: Option to set the date or time or day
        :type opt: str
        :return: True if set is successful
        :rtype: bool
        """
        cmd_out = self._console.execute_command(f"date {opt} '{date_string}'")
        return date_string in cmd_out and "invalid date" not in cmd_out

    def send_mldv2_report(
        self, mcast_group_record: MulticastGroupRecord, count: int
    ) -> None:
        """Send an MLDv2 report with desired multicast record.

        Multicast source and group must be IPv6 addresses.
        Multicast sources need to be non-multicast addresses and
        group address needs to be a multicast address.

        Implementation relies on a custom send_mld_report
        script based on scapy.

        :param mcast_group_record: MLDv2 multicast group record
        :type mcast_group_record: MulticastGroupRecord
        :param count: num of packets to send in 1s interval
        :type count: int
        :raises CodeError: if send_mld_report command fails
        """
        command = f"send_mld_report -i {self.eth_interface} -c {count}"
        out = self._send_multicast_report(command, mcast_group_record)
        if f"Sent {count} packets" not in out:
            msg = f"Failed to execute send_mld_report command:\n{out}"
            raise CodeError(msg)

    def _send_multicast_report(
        self, command: str, mcast_group_record: MulticastGroupRecord
    ) -> str:
        args = ""
        for sources, group, rtype in mcast_group_record:
            src = ",".join(sources)
            args += f'-mr "{src};{group};{rtype.value} "'

        out = self._console.execute_command(f"{command} {args}")
        if "Traceback" in out:
            msg = f"Failed to send the report!!\n{out}"
            raise CodeError(msg)
        return out

    def set_static_ip(
        self,
        interface: str,
        ip_address: IPv4Address,
        netmask: IPv4Address,
    ) -> None:
        """Set given static ip for the LAN.

        :param interface: interface name
        :type interface: str
        :param ip_address: static ip address
        :type ip_address: IPv4Address
        :param netmask: netmask
        :type netmask: IPv4Address
        :raises CodeError: When setting did not work
        """
        # TODO: use sudo shell if needed BOARDFARM-5105
        self._console.execute_command(
            f"ifconfig {interface} {ip_address} netmask {netmask} up"
        )
        ip = self.ipv4_addr
        if ip != ip_address:
            err_msg = f"Running IP: {ip=} is different than expected: {ip_address=}"
            raise CodeError(err_msg)

    def del_default_route(self, interface: str | None = None) -> None:
        """Remove the default gateway.

        :param interface: interface name, default to None
        :type interface: str | None
        """
        # TODO: use sudo shell if needed BOARDFARM-5105
        interface = f"dev {interface}" if interface else ""
        self._console.execute_command(f"ip route del default {interface}")

    def set_default_gw(self, ip_address: IPv4Address, interface: str) -> None:
        """Set given ip address as default gateway address for given interface.

        :param ip_address: gateway ip address
        :type ip_address: IPv4Address
        :param interface: interface name
        :type interface: str
        :raises CodeError: when failing to remove the existing route
        :raises CodeError: when the route is not correctly set
        """
        # TODO: use sudo shell if needed BOARDFARM-5105
        self._console.execute_command("ip route del default")

        out = self._console.execute_command("ip route show default")
        if out[1:]:
            msg = (
                f"Failed to remove existing defualt route {out}, "
                "unable to proceed with set default gatway command "
            )
            raise CodeError(msg)
        self._console.execute_command(
            f"route add default gw {ip_address} dev {interface}"
        )
        out = self._console.execute_command("ip route show default")
        if str(ip_address) not in out.lower():
            err_msg = f"Failed to add default route, ip route output: {out}"
            raise CodeError(err_msg)
        __LOGGER.debug("The route is configured successfully .")

    def start_nping(  # pylint: disable=too-many-arguments # noqa: PLR0913
        self,
        interface_ip: str,
        ipv6_flag: bool,
        extra_args: str,
        port_range: str,
        hit_count: str,
        rate: str,
        mode: str,
    ) -> str:
        """Perform nping.

        :param interface_ip: interface ip addr
        :type interface_ip: str
        :param ipv6_flag: flag if ipv6 addr to be used
        :type ipv6_flag: bool
        :param extra_args: any extra arguments
        :type extra_args: str
        :param port_range: target port range
        :type port_range: str
        :param hit_count: the number of times to target each host
        :type hit_count: str
        :param rate: num of packets per second to send
        :type rate: str
        :param mode: probe mode. tcp/udp/icmp etc protocol
        :type mode: str
        :return: process id
        :rtype: str
        :raises ValueError: if unable to start nping.
        """
        ipv6_option = "-6" if ipv6_flag else ""
        output = self._console.execute_command(
            f"nping -{mode} -c {hit_count} -p {port_range} {ipv6_option} {interface_ip}"
            f" --rate {rate} -g 80 {extra_args} &"
        )
        if output:
            pid = re.search(r"(\[\d+\]\s(\d+))", output)[2]
            process_status = self._console.execute_command(f"ps --pid {pid} -o stat=")
            if process_status and process_status != "T":
                return pid
        msg = "Unable to start nping"
        raise ValueError(msg)

    def stop_nping(self, process_id: str) -> None:
        """Stop nping process running in background.

        :param process_id: process id of nping
        :type process_id: str
        :raises BoardfarmException: when unable to stop process
        """
        for _ in range(3600):
            if self._console.execute_command(f"ps --pid {process_id} -o stat=") != "":
                sleep(10)
                continue
            break
        else:
            __LOGGER.debug(
                "The nping process didn't complete in given time,"
                " killing it to avoid having it in hung state"
            )
            self._console.execute_command(f"kill -9 {process_id}")
            self._console.execute_command("sync")
        if self._console.execute_command("pgrep nping").splitlines():
            msg = "Unable to stop nping process"
            raise BoardfarmException(msg)

    def hping_flood(
        self,
        protocol: str,
        target: str,
        packet_count: str,
        extra_args: str | None = None,
        pkt_interval: str = "",
    ) -> str:
        """Validate SYN, UDP and ICMP flood operation.

        :param protocol: mode, for ex 'S': syn-flood '1': ping-flood (icmp) '2': udp
        :type protocol: str
        :param target: target IP addr
        :type target: str
        :param packet_count: number of packets to be transmitted.
        :type packet_count: str
        :param extra_args: extra arguments to be passed, defaults to None
        :type extra_args: str
        :param pkt_interval: wait for X microseconds before sending next packet uX,
            defaults to "", uX for X microseconds, for example -i u1000
        :type pkt_interval: str
        :return: command output
        :rtype: str
        """
        if pkt_interval:
            pkt_interval = f"-i {pkt_interval}"
        return self._console.execute_command(
            f"sudo hping3 {pkt_interval} -c {packet_count} -{protocol} {target} "
            f"{extra_args}"
        )

    @property
    def nw_utility(self) -> NetworkUtility:
        """Returns Network utility instance.

        :return: network utiluty instance with console object
        :rtype: NetworkUtility
        """
        self._nw_utility = NetworkUtility(self._console)
        return self._nw_utility

    def hostname(self) -> str:
        """Get the hostname of the device.

        :return: hostname of the device
        :rtype: str
        """
        return self._console.execute_command("echo $HOSTNAME")

    def get_process_id(self, process_name: str) -> list[str] | None:
        """Return the process id to the device.

        :param process_name: name of the process
        :type process_name: str
        :return: process id if the process exist, else None
        :rtype: list[str] | None
        """
        pid_output = self._console.execute_command(f"pidof {process_name}").strip()
        return pid_output.split(" ") if pid_output else None

    def kill_process(self, pid: int, signal: int) -> None:
        """Terminate the running process based on the process id.

        :param pid: process id
        :type pid: int
        :type signal: signal number to terminate the process
        :type signal: int
        :raises ValueError: if unable to kill the process
        """
        self._console.execute_command(f"kill -{signal} {pid}")
        if str(pid) in self._console.execute_command(f"ps -p {pid}"):
            msg = f"Unable to kill process {pid}"
            raise ValueError(msg)
