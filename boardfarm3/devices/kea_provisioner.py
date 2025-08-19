"""Kea Ethernet Based Provisioner."""

from __future__ import annotations

import logging
import re
import secrets
from argparse import Namespace
from copy import deepcopy
from ipaddress import ip_address, ip_interface, ip_network
from json import dumps
from operator import itemgetter
from time import sleep
from typing import TYPE_CHECKING, Any

import pexpect

from boardfarm3 import hookimpl
from boardfarm3.configs import (
    KIA_DHCP_IPV4_CONFIG_TEMPLATE,
    KIA_DHCP_IPV6_CONFIG_TEMPLATE,
)
from boardfarm3.exceptions import (
    BoardfarmException,
    ContingencyCheckError,
    DeviceBootFailure,
    SCPConnectionError,
)
from boardfarm3.lib.connection_factory import connection_factory
from boardfarm3.lib.connections.local_cmd import LocalCmd
from boardfarm3.lib.networking import IptablesFirewall
from boardfarm3.lib.networking import start_tcpdump as start_tcp_dump
from boardfarm3.lib.networking import stop_tcpdump as stop_tcp_dump
from boardfarm3.lib.shell_prompt import KEA_PROVISIONER_SHELL_PROMPT
from boardfarm3.templates.provisioner import Provisioner
from boardfarm3.templates.wan import WAN

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.custom_typing.dhcp import (
        DHCPServicePools,
        DHCPSubOption,
        DHCPv4Options,
        DHCPv6Options,
        DHCPVendorOptions,
    )
    from boardfarm3.lib.device_manager import DeviceManager


_LOGGER = logging.getLogger(__name__)


class KeaProvisioner(Provisioner):
    """Kea based provisioner Device."""

    _default_lifetime: int = 43200
    _renewal_time: int = 3600
    _rebind_time: int = 5400
    eth_interface = "eth1"

    def __init__(self, config: dict[str, Any], cmdline_args: Namespace) -> None:
        """Instance initialization.

        :param config: configuration from inventory
        :type config: Dict
        :param cmdline_args: command line args
        :type cmdline_args: Namespace
        """
        super().__init__(config=config, cmdline_args=cmdline_args)
        self._pref_vlan = self._config.get("preferred_vlan", "untagged")
        self._console: BoardfarmPexpect = None
        self._shell_prompt = [KEA_PROVISIONER_SHELL_PROMPT]
        self.dhcpv4_options: dict[DHCPServicePools, DHCPv4Options] = {}
        self.dhcpv6_options: dict[DHCPServicePools, DHCPv6Options] = {}
        self._password = self._config.get("password", "bigfoot1")
        self._firewall: IptablesFirewall = None

    @property
    def _supported_vsio_options(self) -> list[DHCPSubOption]:
        """Provide vsio supported suboptions.

        The ENV shall provide user-defined VSIO options that need
        to be cross-checked with the pre-configured options
        defined in DHCP server.

        This method shall provide the list of pre-configured VSIO suboptions.

        :return: List of VSIO suboptions
        :rtype: list[DHCPSubOption]
        """
        return [
            {"name": "acs-url", "sub-option-code": 1, "data": ""},
            {"name": "provisioning-code", "sub-option-code": 2, "data": ""},
        ]

    @property
    def _supported_vivso_options(self) -> DHCPVendorOptions:
        """Provide vivso supported suboptions.

        The ENV shall provide user-defined VIVSO options that need
        to be cross-checked with the pre-configured options
        defined in DHCP server.

        This method shall provide the list of pre-configured VIVSO suboptions.

        :return: Vendor ID and VIVSO sub-options
        :rtype: DHCPVendorOptions
        """
        return {
            "vendor-id": 3561,
            "sub-options": [
                {"name": "acs-url", "sub-option-code": 1, "data": ""},
                {"name": "provisioning-code", "sub-option-code": 2, "data": ""},
            ],
        }

    def _is_env_vsio_supported(
        self,
        requested_vsio_options: list[DHCPSubOption],
    ) -> bool:
        getter = itemgetter("name", "sub-option-code")
        return set(map(getter, self._supported_vsio_options)) == set(
            map(getter, requested_vsio_options),
        )

    def _is_env_vivso_supported(
        self,
        requested_vivso_options: DHCPVendorOptions,
    ) -> bool:
        if not requested_vivso_options:
            return False

        getter = itemgetter("name", "sub-option-code")
        return (
            set(map(getter, self._supported_vivso_options["sub-options"]))
            == set(map(getter, requested_vivso_options["sub-options"]))
            and self._supported_vivso_options["vendor-id"]
            == requested_vivso_options["vendor-id"]
        )

    def _get_suboption_configuration(
        self,
        options: list[DHCPSubOption],
        space: str,
    ) -> list[dict[str, Any]]:
        option_data = []
        for option in options:
            if option["name"] == "acs-url":
                # Encode to binary with space char in case of empty data
                if not option["data"].strip():
                    option["data"] = " "
                option["data"] = option["data"].encode().hex()

            option_data.append(
                {
                    "always-send": True,
                    "name": option["name"],
                    "space": space,
                    "data": option["data"],
                },
            )
        return option_data

    def _get_vsio_configuration(
        self,
        vsio_options: list[DHCPSubOption],
    ) -> list[dict[str, Any]]:
        vsio_config = []
        vsio_config.append(
            {"always-send": True, "name": "vendor-encapsulated-options"},
        )
        vsio_config.extend(
            self._get_suboption_configuration(
                vsio_options,
                space="vendor-encapsulated-options-space",
            ),
        )
        return vsio_config

    def _get_vivso_configuration(
        self,
        vivso_options: DHCPVendorOptions,
        ipv6: bool = False,
    ) -> list[dict[str, Any]]:
        vivso_config = []
        option_name = "vendor-opts" if ipv6 else "vivso-suboptions"

        vivso_config.append(
            {
                "always-send": True,
                "data": f"{vivso_options['vendor-id']}",
                "name": option_name,
            },
        )

        vivso_config.extend(
            self._get_suboption_configuration(
                vivso_options["sub-options"],
                space=f"vendor-{vivso_options['vendor-id']}",
            ),
        )
        return vivso_config

    @property
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT.

        :return: name of the dut interface
        :rtype: str
        """
        return self.eth_interface

    def tshark_read_pcap(  # pylint: disable=duplicate-code
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
            self.console.sudo_sendline(f"rm {fname}")
            self.console.expect(
                self._shell_prompt  # type:ignore[attr-defined] # pylint: disable=maybe-no-member
            )
        return output

    # pylint: disable=R0801
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
        return start_tcp_dump(
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
        stop_tcp_dump(self._console, process_id=process_id)

    def _run_command_with_args(  # pylint: disable=duplicate-code
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
        self.console.sudo_sendline(read_command)
        self.console.expect(
            self._shell_prompt,  # type:ignore[attr-defined] # pylint: disable=maybe-no-member
            timeout=timeout,
        )
        return self.console.before

    def scp_device_file_to_local(self, local_path: str, source_path: str) -> None:
        """Copy a local file from a server using SCP.

        :param local_path: local file path
        :param source_path: source path
        """
        _username = self.config.get("username", "root")
        source_path = f"{_username}@{self.config.get('ipaddr')}:{source_path}"
        self._scp_local_files(source=source_path, destination=local_path)

    # pylint: disable=duplicate-code
    def _scp_local_files(self, source: str, destination: str) -> None:
        """Perform file copy on local console using SCP.

        :param source: source file path
        :param destination: destination file path
        :raises SCPConnectionError: when SCP command return non-zero exit code
        """
        _password = self.config.get("password", "bigfoot1")
        args = [
            f"-P {self.config.get('port', '22')}",
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
            session.sendline(_password)
        session.expect(pexpect.EOF, timeout=90)
        if session.wait() != 0:
            msg = f"Failed to SCP file from {source} to {destination}"
            raise SCPConnectionError(
                msg,
            )

    # pylint: enable=duplicate-code

    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        """
        self.console.execute_command(f"rm {filename}")

    def _get_dhcp_ipv4_config(
        self,
        cpe_mac: str,
        dhcpv4_options: DHCPv4Options,
    ) -> dict[str, Any]:
        config: dict[str, Any] = deepcopy(KIA_DHCP_IPV4_CONFIG_TEMPLATE)
        iface = self._config["vlans"][self._pref_vlan]["iface"]
        cpe_addr = self._config["vlans"][self._pref_vlan].get("cpe_ipv4")

        # Defaults
        config["Dhcp4"]["interfaces-config"] = {"interfaces": [iface]}
        config["Dhcp4"]["valid-lifetime"] = self._default_lifetime
        config["Dhcp4"]["renew-timer"] = self._renewal_time
        config["Dhcp4"]["rebind-timer"] = self._rebind_time

        # Subnet configuration handled based on preferred-vlan from INV
        # TODO: VLAN/subnet configuration should be based on country profile.
        subnet = ip_interface(self._config["vlans"][self._pref_vlan]["ipv4"])
        config["Dhcp4"]["subnet4"][0]["subnet"] = str(subnet)
        config["Dhcp4"]["subnet4"][0]["id"] = secrets.choice(range(1024))
        config["Dhcp4"]["subnet4"][0]["interface"] = iface
        config["Dhcp4"]["subnet4"][0]["pools"] = [
            {
                "pool": f"{subnet.network[10]} - {subnet.network[20]}",
                "client-class": "VENDOR_CLASS_BF_LAN_CPE",
            },
            {
                "pool": f"{subnet.network[21]} - {subnet.network[50]}",
            },
        ]

        # Host Reservation if cpe_addr is provided
        if cpe_addr:
            config["Dhcp4"]["subnet4"][0]["reservations"].append(
                {"hw-address": cpe_mac, "ip-address": cpe_addr},
            )

            # Add Lease class in reservations if needed
            if lease := dhcpv4_options.get("valid-lifetime"):
                config["Dhcp4"]["subnet4"][0]["reservations"][0]["client-classes"] = [
                    lease
                ]

        # Add router option
        config["Dhcp4"]["subnet4"][0]["option-data"].append(
            {"name": "routers", "data": f"{subnet.network[1]}"},
        )

        # DNS server option configuration
        if dns := dhcpv4_options.get("dns-server"):
            config["Dhcp4"]["subnet4"][0]["option-data"].append(
                {"name": "domain-name-servers", "data": dns},
            )

        # NTP server option configuration
        if ntp := dhcpv4_options.get("ntp-server"):
            config["Dhcp4"]["subnet4"][0]["option-data"].append(
                {"name": "ntp-servers", "data": ntp},
            )

        # Add VSIO if requested via ENV
        if (vsio := dhcpv4_options.get("vsio")) and self._is_env_vsio_supported(vsio):
            config["Dhcp4"]["subnet4"][0]["option-data"].extend(
                self._get_vsio_configuration(vsio),
            )

        # Add VIVSO if requested via ENV
        if (vivso := dhcpv4_options.get("vivso")) and self._is_env_vivso_supported(
            vivso,
        ):
            config["Dhcp4"]["subnet4"][0]["option-data"].extend(
                self._get_vivso_configuration(vivso),
            )
        return config

    def _get_dhcp_ipv6_config(
        self,
        cpe_mac: str,
        dhcpv6_options: DHCPv6Options,
    ) -> dict[str, Any]:
        config: dict[str, Any] = deepcopy(KIA_DHCP_IPV6_CONFIG_TEMPLATE)
        iface = self._config["vlans"][self._pref_vlan]["iface"]
        pd_pool = ip_network(self._config["vlans"][self._pref_vlan]["cpe_pd"])
        subnet = ip_interface(self._config["vlans"][self._pref_vlan]["ipv6"])
        cpe_addr6 = self._config["vlans"][self._pref_vlan].get("cpe_ipv6")

        duid = (
            f"000200000de9{self._config['duid_en'].encode('UTF-8').hex()}"
            if self._config.get("duid_en")
            else f"00:03:00:01:{cpe_mac}"
        )

        # Defaults
        config["Dhcp6"]["valid-lifetime"] = self._default_lifetime
        config["Dhcp6"]["renew-timer"] = self._renewal_time
        config["Dhcp6"]["rebind-timer"] = self._rebind_time
        config["Dhcp6"]["interfaces-config"] = {"interfaces": [iface]}

        # Subnet configuration handled based on preferred-vlan from INV
        # TODO: VLAN/subnet configuration should be based on country profile.
        config["Dhcp6"]["subnet6"][0]["subnet"] = str(subnet)
        config["Dhcp6"]["subnet6"][0]["id"] = secrets.choice(range(1024))
        config["Dhcp6"]["subnet6"][0]["interface"] = iface
        config["Dhcp6"]["subnet6"][0]["pools"] = [
            {
                "pool": f"{subnet.network[512]} - {subnet.network[767]}",
                "client-class": "VENDOR_CLASS_BF_LAN_CPE",
            },
            {
                "pool": f"{subnet.network[256]} - {subnet.network[511]}",
            },
        ]
        config["Dhcp6"]["subnet6"][0]["pd-pools"].append(
            {
                "prefix": str(pd_pool.network_address),
                "prefix-len": 48,
                "delegated-len": pd_pool.prefixlen,
            },
        )

        if cpe_addr6:
            config["Dhcp6"]["subnet6"][0]["reservations"] = [
                {
                    "duid": duid,
                    "ip-addresses": [cpe_addr6],
                },
            ]

            # Add Lease class in reservations if needed
            if lease := dhcpv6_options.get("valid-lifetime"):
                config["Dhcp6"]["subnet6"][0]["reservations"][0]["client-classes"] = [
                    lease
                ]

        # DNS server option configuration
        if dns := dhcpv6_options.get("dns-server"):
            config["Dhcp6"]["subnet6"][0]["option-data"].append(
                {"name": "dns-servers", "data": dns},
            )

        # NTP server option configuration
        if ntp := dhcpv6_options.get("ntp-server"):
            ntp = "".join(
                f"00010010{ip_address(ip6).exploded.replace(':', '')}"
                for ip6 in ntp.split(",")
            )
            config["Dhcp6"]["subnet6"][0]["option-data"].append(
                {
                    "name": "ntp-servers",
                    "data": ntp,
                },
            )

        # Add VIVSO if requested via ENV
        if (vivso := dhcpv6_options.get("vivso")) and self._is_env_vivso_supported(
            vivso,
        ):
            config["Dhcp6"]["subnet6"][0]["option-data"].extend(
                self._get_vivso_configuration(vivso, ipv6=True),
            )

        return config

    def _connect(self) -> None:
        if self._console is None:
            self._console = connection_factory(
                self._config.get("connection_type"),
                f"{self.device_name}.console",
                username=self._config.get("username", "root"),
                password=self._password,
                ip_addr=self._config.get("ipaddr"),
                port=self._config.get("port", "22"),
                shell_prompt=self._shell_prompt,
                save_console_logs=self._cmdline_args.save_console_logs,
            )

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot the KEA provisioner."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        self._console.login_to_server(self._password)

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm hook implementation to initialize the KEA provisioner."""
        _LOGGER.info("Initializing %s(%s) device", self.device_name, self.device_type)
        self._connect()
        self._console.login_to_server(self._password)

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown the KEA provisioner."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        if self._console is not None:
            self._console.close()
            self._console = None

    @hookimpl
    def contingency_check(self) -> None:
        """Make sure the KeaProvisioner is working fine before use.

        :raises ContingencyCheckError: if the device console is not responding
        """
        if self._cmdline_args.skip_contingency_checks:
            return
        _LOGGER.info("Contingency check %s(%s)", self.device_name, self.device_type)
        if "FOO" not in self._console.execute_command("echo FOO"):
            msg = "KeaProvisioner device console in not responding"
            raise ContingencyCheckError(msg)

    @hookimpl
    def boardfarm_server_configure(self, device_manager: DeviceManager) -> None:
        """Boardfarm hook implementation to configure the KEA provisioner.

        The KEA server configuration will only deal with reading the
        necessary options from ENV.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        """
        # Configure KEA if skip_boot is not provided on command line.
        if self._cmdline_args.skip_boot:
            return

        wan: WAN = device_manager.get_device_by_type(
            WAN,  # type:  ignore[type-abstract]
        )

        # Fetch ENV details for provisioning CPE
        dhcp_options = self._config.get("dhcp_options", {})

        # FIXME: BOARDFARM-4940 DHCP options specified before # noqa: FIX001
        # ENV SCHEMA 3.2 do not differentiate according to service VLAN they
        # support.
        # i.e. they do not have a data/voice/mng key for each options
        # So fo the time being we will update this ourselves as
        # in case of ethernet everything goes under data
        self.dhcpv4_options = {"data": dhcp_options.get("dhcpv4", {})}
        self.dhcpv6_options = {"data": dhcp_options.get("dhcpv6", {})}

        # Need to provide DNS as WAN container if missing from ENV
        # By default we do not specify DNS server to be used in INV.
        self.dhcpv4_options["data"].setdefault(
            "dns-server",
            self._config.get("dns-server") or wan.get_eth_interface_ipv4_address(),
        )
        self.dhcpv6_options["data"].setdefault(
            "dns-server",
            self._config.get("dns-server6") or wan.get_eth_interface_ipv6_address(),
        )

    @property
    def console(self) -> BoardfarmPexpect:
        """Returns Provisioner console.

        :return: console
        :rtype: BoardfarmPexpect
        """
        return self._console

    @property
    def firewall(self) -> IptablesFirewall:
        """Returns Firewall component instance.

        :return: firewall component instance with console object
        :rtype: IptablesFirewall
        """
        self._firewall = IptablesFirewall(self._console)
        return self._firewall

    def provision_cpe(
        self,
        cpe_mac: str,
        dhcpv4_options: dict[DHCPServicePools, DHCPv4Options],
        dhcpv6_options: dict[DHCPServicePools, DHCPv6Options],
    ) -> None:
        """Configure the KEA provisioner with the CPE values.

        Configure the provisioner with the IPv4 and IPv6 values that are returned
        to the CPE on a DHCPv4 Offer/ACK - DHCPv6 Advertise/Reply.
        Currently the ETTH devices are in a 1 to 1 configuration:
        1 CPE to 1 Provisioner (this could change).

        :param cpe_mac: CPE mac address
        :type cpe_mac: str
        :param dhcpv4_options: DHCPv4 Options with ACS, NTP, DNS details
        :type dhcpv4_options: dict[DHCPServicePools, DHCPv4Options]
        :param dhcpv6_options: DHCPv6 Options with ACS, NTP, DNS details
        :type dhcpv6_options: dict[DHCPServicePools, DHCPv6Options]
        """
        dhcpv4_options = dhcpv4_options or self.dhcpv4_options
        dhcpv6_options = dhcpv6_options or self.dhcpv6_options

        config: str = dumps(
            self._get_dhcp_ipv4_config(
                cpe_mac=cpe_mac,
                dhcpv4_options=dhcpv4_options["data"],
            ),
            indent=4,
        )
        self._console.sendline(
            f"cat > /etc/kea/kea-dhcp4.conf << EOF\n{config}\nEOF",
        )
        self._console.expect(self._shell_prompt)
        config = dumps(
            self._get_dhcp_ipv6_config(
                cpe_mac=cpe_mac,
                dhcpv6_options=dhcpv6_options["data"],
            ),
            indent=4,
        )
        self._console.sendline(
            f"cat > /etc/kea/kea-dhcp6.conf << EOF\n{config}\nEOF",
        )
        self._console.expect(self._shell_prompt)
        self._restart_dhcp_server()

    def _restart_dhcp_server(self) -> None:
        self._console.execute_command("keactrl stop")
        sleep(2)
        out = self._console.execute_command("keactrl start -s dhcp4")
        if re.match(r"INFO/keactrl: Starting.*-dhcp4.*kea-dhcp4\.conf", out) is None:
            msg = f"Failed to start IPv4 KEA provisioner: {out}"
            raise DeviceBootFailure(msg)
        out = self._console.execute_command("keactrl start -s dhcp6")
        if re.match(r"INFO/keactrl: Starting.*-dhcp6.*kea-dhcp6\.conf", out) is None:
            msg = f"Failed to start IPv6 KEA provisioner: {out}"
            raise DeviceBootFailure(msg)

    def get_interactive_consoles(self) -> dict[str, BoardfarmPexpect]:
        """Get interactive consoles of the device.

        :returns: interactive consoles of the device
        :rtype: dict[str, BoardfarmPexpect]
        """
        return {} if self._console is None else {"console": self._console}


if __name__ == "__main__":
    # stubbed instantation of the device
    # this would throw a linting issue in case the device does not follow the template

    KeaProvisioner(config={}, cmdline_args=Namespace())
