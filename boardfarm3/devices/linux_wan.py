"""Boardfarm WAN device module."""

from __future__ import annotations

import logging
import random
import re
import string
from argparse import Namespace
from ipaddress import IPv4Interface, IPv6Interface
from typing import TYPE_CHECKING, Any

import jc

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import ContingencyCheckError
from boardfarm3.lib.multicast import Multicast
from boardfarm3.lib.networking import IptablesFirewall, NSLookup
from boardfarm3.lib.regexlib import AllValidIpv6AddressesRegex
from boardfarm3.lib.shell_prompt import LINUX_WAN_BASH_SHELL_PROMPT
from boardfarm3.lib.utils import get_value_from_dict
from boardfarm3.templates.cpe import CPE
from boardfarm3.templates.wan import WAN

if TYPE_CHECKING:
    from collections.abc import Iterator

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods,too-many-instance-attributes
class LinuxWAN(LinuxDevice, WAN):  # pylint: disable=R0902
    """Boardfarm WAN device."""

    _tftpboot_dir = "/tftpboot"

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize LinuxWAN device.

        :param config: device configuration
        :type config: dict
        :param cmdline_args: command line arguments
        :type cmdline_args: Namespace
        """
        self._static_route = ""
        self._wan_dhcp = False
        self._wan_no_eth0 = False
        self._wan_dhcp_server = False
        self._wan_dhcpv6 = False
        self._dante = False
        self._multicast: Multicast = None
        self._board_prompt = LINUX_WAN_BASH_SHELL_PROMPT
        super().__init__(config, cmdline_args)
        self._firewall: IptablesFirewall = None
        self._nslookup: NSLookup = None

    def _setup_wan(self, device_manager: DeviceManager) -> None:  # noqa: C901 # BOARDFARM-4957
        options = self._parse_device_suboptions()
        for opt, opt_val in options.items():
            if opt == "internet-access-on-mgmt":
                self._internet_access_cmd = "mgmt"
            elif opt == "wan-dhcp-client":
                self._wan_dhcp = True
            elif opt == "dante":
                self.start_danteproxy()
            elif opt == "wan-no-eth0":
                self._wan_no_eth0 = True
            elif opt == "wan-no-dhcp-server":
                self._wan_dhcp_server = False
            elif opt == "wan-dhcp-client-v6":
                self._wan_dhcpv6 = True
            elif opt == "wan-static-ipv6":
                ipv6_interface = IPv6Interface(opt_val)
                # we are bypassing this for now
                # (see http://patchwork.ozlabs.org/patch/117949/)
                self._console.execute_command(
                    f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0",
                )
                if opt_val in self.get_interface_ipv6addr(self.iface_dut):
                    # If addresses are deleted they will remove the ipv6 route
                    # If the addresses match do not delete.
                    continue
                self._console.execute_command(
                    f"ip -6 addr del {ipv6_interface} dev {self.iface_dut}",
                )
                self._console.execute_command(
                    f"ip -6 addr add {ipv6_interface} dev {self.iface_dut}",
                )
            elif opt == "wan-static-ip":
                ipv4_interface = IPv4Interface(opt_val)
                self._console.execute_command(
                    f"ip -4 addr del {ipv4_interface} dev {self.iface_dut}",
                )
                self._console.execute_command(
                    f"ip -4 addr add {ipv4_interface} dev {self.iface_dut}",
                )
            # Fix to configure DNS option only on device that runs TFTP
            elif opt == "dns-server":
                self._configure_dns(device_manager)

        self._setup_static_routes()

    def _configure_dns(self, device_manager: DeviceManager) -> None:
        dns_hosts = []
        for device in device_manager.get_devices_by_type(LinuxDevice).values():
            device_suboptions = device._parse_device_suboptions()  # noqa: SLF001 pylint: disable=W0212
            name = device.device_name
            ip4_addr = device_suboptions.get("wan-static-ip", "")
            ip6_addr = device_suboptions.get("wan-static-ipv6", "")
            if ip4_addr:
                ip = IPv4Interface(ip4_addr).ip
                dns_hosts.append(f"{ip}    {name}.boardfarm.com")
                dns_hosts.append(f"{ip}    {name}_ipv4.boardfarm.com")
            if ip6_addr:
                ip6 = IPv6Interface(ip6_addr).ip
                dns_hosts.append(f"{ip6}    {name}.boardfarm.com")
                dns_hosts.append(f"{ip6}    {name}_ipv6.boardfarm.com")
        if dns_hosts:
            self._console.sendline("cat > /etc/dnsmasq.hosts << EOF")
            self._console.sendline("\n".join(dns_hosts))
            self._console.sendline("EOF")
            self._console.expect(self._shell_prompt)
        self._console.execute_command("service dnsmasq restart")

    @hookimpl
    def boardfarm_server_boot(self, device_manager: DeviceManager) -> None:
        """Boardfarm hook implementation to boot WAN device.

        :param device_manager: Device Manager
        :type device_manager: DeviceManager
        """
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        self._add_multicast_to_linux_wan()
        self._setup_wan(
            device_manager
        )  # to be revisited when docker factory is implemented

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm hook implementation to initialize WAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        self._add_multicast_to_linux_wan()

    @hookimpl
    async def boardfarm_skip_boot_async(self) -> None:
        """Boardfarm hook implementation to initialize LAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        await self._connect_async()
        self._add_multicast_to_linux_wan()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown WAN device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    @hookimpl
    def contingency_check(
        self,
        env_req: dict[str, Any],
        device_manager: DeviceManager,
    ) -> None:
        """Make sure the WAN is working fine before use.

        :param env_req: test env request
        :type env_req: dict[str, Any]
        :param device_manager: device manager instance
        :type device_manager: DeviceManager
        """
        if self._cmdline_args.skip_contingency_checks:
            return
        _LOGGER.info("Contingency check %s(%s)", self.device_name, self.device_type)
        self.get_eth_interface_ipv4_address()
        self.get_eth_interface_ipv6_address()
        # Perform DNS service check
        if acs_server_config := get_value_from_dict("ACS_SERVER", env_req):
            self._validate_dns_env_request(
                acs_server_config,
                device_manager.get_device_by_type(
                    CPE,  # type:ignore[type-abstract]
                ).sw.get_provision_mode(),
            )

    def _add_env_variable(self, env_param: dict[str, str], sep: str = ",") -> None:
        """Export an ENV param on the WAN device.

        :param env_param: ENV key:value pair that needs to be added.
        :type env_param: dict[str,str]
        :param sep: Seperator used to append values to existing ENV keys
        :type sep: str
        """
        env_output = jc.parse("env", self._console.execute_command("env"), raw=True)
        for env_key, env_val in env_param.items():
            if env_key not in env_output:
                self._console.execute_command(f"export {env_key}={env_val}")
                continue

            if env_val not in env_output[env_key]:  # type: ignore[index, call-overload]
                self._console.execute_command(
                    f"export {env_key}=${{{env_key}}}{sep}{env_val}",
                )

    def _validate_dns_env_request(
        self,
        acs_server_config: dict[str, dict[str, str]],
        prov_mode: str,
    ) -> None:
        output = NSLookup(self._console).nslookup("acs_server.boardfarm.com")
        ping_status = {
            "ipv4": {"reachable": 0, "unreachable": 0},
            "ipv6": {"reachable": 0, "unreachable": 0},
        }
        for ip_address in output.get("domain_ip_addr", []):
            ip_version = (
                "ipv6" if re.match(AllValidIpv6AddressesRegex, ip_address) else "ipv4"
            )
            if ip_version != prov_mode:
                continue
            if self.ping(ip_address, ping_count=2):
                ping_status[ip_version]["reachable"] += 1
            else:
                ping_status[ip_version]["unreachable"] += 1
        for ip_version, item in ping_status.items():
            if ip_version not in acs_server_config or ip_version != prov_mode:
                continue
            for status, value in item.items():
                if status not in acs_server_config[ip_version]:
                    continue
                if acs_server_config[ip_version][status] != value:
                    msg = (
                        f"DNS check failed for {ip_version} {status} servers "
                        "- requested: {acs_server_config[ip_version][status]}, "
                        "actual: {value}"
                    )
                    raise ContingencyCheckError(
                        msg,
                    )

    @property
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT.

        :returns: the DUT interface name
        :rtype: str
        """
        return self.eth_interface

    @property
    def multicast(self) -> Multicast:
        """Return multicast component instance.

        :return: multicast component instance
        :rtype: Multicast
        """
        return self._multicast

    @property
    def console(self) -> BoardfarmPexpect:
        """Return wan console.

        :return: console
        :rtype: BoardfarmPexpect
        """
        return self._console

    @property
    def rssh_username(self) -> str:
        """Return the WAN username for Reverse SSH.

        :return: WAN username
        :rtype: str
        """
        return (
            self._config.get("rssh_username")
            if "rssh_username" in self._config
            else "root"
        )

    @property
    def rssh_password(self) -> str:
        """Return the WAN password for Reverse SSH.

        :return: WAN password
        :rtype: str
        """
        return (
            self._config.get("rssh_password")
            if "rssh_password" in self._config
            else "bigfoot1"
        )

    @property
    def http_proxy(self) -> str:
        """SOCKS5 dante proxy address, e.g http://{proxy_ip}:{proxy_port}/.

        :return: dante proxy address
        :rtype: str
        """
        return self._config.get("http_proxy")

    @property
    def firewall(self) -> IptablesFirewall:
        """Returns Firewall component instance.

        :return: firewall component instance with console object
        :rtype: IptablesFirewall
        """
        self._firewall = IptablesFirewall(self._console)
        return self._firewall

    @property
    def nslookup(self) -> NSLookup:
        """Returns NSLookup utility instance.

        :return: nslookup utility instance with console object
        :rtype: NSLookup
        """
        self._nslookup = NSLookup(self._console)
        return self._nslookup

    def copy_local_file_to_tftpboot(self, local_file_path: str) -> None:
        """SCP local file to tftpboot directory.

        :param local_file_path: local file path
        :type local_file_path: str
        """
        self.scp_local_file_to_device(local_file_path, self._tftpboot_dir)

    def download_image_to_tftpboot(self, image_uri: str) -> str:
        """Download image from URL to tftpboot directory.

        :param image_uri: image file URI
        :type image_uri: str
        :returns: name of the image in tftpboot
        :rtype: str
        """
        filename = "".join(
            random.choice(string.ascii_lowercase)  # noqa: S311
            for _ in range(10)
        )
        tempfile = self.download_file_from_uri(image_uri, self._tftpboot_dir)
        self._console.execute_command(
            f"mv {self._tftpboot_dir}/{tempfile} {self._tftpboot_dir}/{filename}",
        )
        return filename

    def execute_snmp_command(self, snmp_command: str, timeout: int = 30) -> str:
        """Execute snmp command.

        :param snmp_command: snmp command
        :type snmp_command: str
        :param timeout: pexpect timeout for the command in seconds, defaults to 30
        :type timeout: int
        :returns: snmp command output
        :rtype: str
        :raises ValueError: when snmp command is invalid
        """
        # Only allowing snmp commands to be executed from wan
        # only wan has snmp utils installed on it.
        if not snmp_command.startswith("snmp"):
            msg = f"{snmp_command!r} is not a SNMP command"
            raise ValueError(msg)
        return self._console.execute_command(snmp_command, timeout=timeout)

    def is_connect_to_board_via_reverse_ssh_successful(
        self,
        rssh_username: str,
        rssh_password: str | None,
        reverse_ssh_port: str,
    ) -> bool:
        """Perform reverse SSH from jump server to CPE.

        The board which needs to be connected using reverse ssh is identifed
        by the reverse_ssh_port

        :param rssh_username: username of the cpe
        :type rssh_username: str
        :param rssh_password: password to login the cpe
        :type rssh_password: str | None
        :param reverse_ssh_port: the port number
        :type reverse_ssh_port: str
        :raises ValueError: when password is provided to login the CPE
        :raises ValueError: when unable to RSSH the CPE
        :return: True if the RSSH is successful, false otherwise
        :rtype: bool
        """
        if rssh_password is not None:
            err_msg = (
                "It is unexpected that a password must be used to connect to the CPE"
            )
            raise ValueError(err_msg)
        ssh_command = (
            f"ssh {rssh_username}@localhost "
            f"-p {reverse_ssh_port} -o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
            "/sbin/ifconfig erouter0"
        )
        output = self._console.execute_command(ssh_command)
        if "erouter0" in output:
            _LOGGER.debug("SSH done from jump server to CPE")
            return True
        if "Connection refused" in output:
            _LOGGER.debug("Unable to SSH from jump server to CPE")
            return False
        error_msg = f"Unable to login the CPE- {ssh_command} {output}"
        raise ValueError(error_msg)

    def get_network_statistics(
        self,
    ) -> dict[str, Any] | list[dict[str, Any]] | Iterator[dict[str, Any]]:
        """Execute netstat command to get the port status.

        Sample block of the output

        .. code-block:: python

            [
                {
                    "proto": "tcp",
                    "recv_q": 0,
                    "send_q": 224,
                    "local_address": "bft-node-cmts1-wan-",
                    "foreign_address": "172.17.132.50",
                    "state": "ESTABLISHED",
                    "kind": "network",
                    "local_port": "ssh",
                    "foreign_port": "51104",
                    "transport_protocol": "tcp",
                    "network_protocol": "ipv4",
                    "foreign_port_num": 51104,
                }
            ]

        :return: parsed output of netstat command
        :rtype: dict[str, Any] | list[dict[str, Any]] | Iterator[dict[str, Any]]
        """
        return jc.parse("netstat", self._console.execute_command("netstat -an"))

    def _add_multicast_to_linux_wan(self) -> None:
        self._multicast = Multicast(
            self.device_name,
            self.iface_dut,
            self._console,
            self._shell_prompt,
        )

    def get_interface_mtu_size(self, interface: str) -> int:
        """Get the MTU size of the interface in bytes.

        :param interface: name of the interface
        :type interface: str
        :return: size of the MTU in bytes
        :rtype: int
        :raises ValueError: when ifconfig data is not available
        """
        if ifconfig_data := jc.parse(
            "ifconfig",
            self._console.execute_command(f"ifconfig {interface}"),
        ):
            return int(ifconfig_data[0]["mtu"])  # type: ignore[index]
        msg = f"ifconfig {interface} is not available"
        raise ValueError(msg)

    def add_route(self, destination: str, gw_interface: str) -> None:
        """Add a route to a destination via a specific gateway interface.

        The method will internally calculate the exit interface's ip address
        before adding the route.
        The gw_interface must be an interface name that exists on the host.

        :param destination: ip address of the destination
        :type destination: str
        :param gw_interface: name of the interface
        :type gw_interface: str
        :raises ValueError: if method was unable to add route
        """
        gw_ipaddress = self.get_interface_ipv4addr(interface=gw_interface)
        self._console.execute_command(
            f"ip route add {destination} via {gw_ipaddress} dev {gw_interface}",
        )
        if self._console.execute_command("echo $?").strip() != "0":
            _LOGGER.error("Failed to add route to %s via %s", destination, gw_ipaddress)
            msg = f"Failed to add route to {destination}"
            raise ValueError(msg)

    def delete_route(self, destination: str) -> None:
        """Delete a route to a destination.

        :param destination: ip address of the destination
        :type destination: str
        """
        self._console.execute_command("sync")
        self._console.execute_command(f"ip route del {destination}")

    def get_hostname(self) -> str:
        """Get the hostname of the device.

        :return: hostname of the device
        :rtype: str
        """
        return self.hostname()


if __name__ == "__main__":
    # stubbed instantation of the device
    # this would throw a linting issue in case the device does not follow the template

    LinuxWAN(config={}, cmdline_args=Namespace())
