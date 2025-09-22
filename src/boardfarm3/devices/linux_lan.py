"""Boardfarm LAN device module."""

from __future__ import annotations

import binascii
import logging
import re
from argparse import Namespace
from ipaddress import AddressValueError, IPv4Address
from typing import TYPE_CHECKING, Any

import jc
import pexpect

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import BoardfarmException, ContingencyCheckError
from boardfarm3.lib.multicast import Multicast
from boardfarm3.lib.networking import IptablesFirewall, NSLookup
from boardfarm3.lib.utils import get_value_from_dict
from boardfarm3.templates.cpe.cpe import CPE
from boardfarm3.templates.lan import LAN

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_config import BoardfarmConfig
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.device_manager import DeviceManager


_LOGGER = logging.getLogger(__name__)
# pylint: disable=too-many-public-methods, too-many-lines


class LinuxLAN(LinuxDevice, LAN):
    """Boardfarm LAN device."""

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize linux LAN device.

        :param config: device configuration
        :type config: dict
        :param cmdline_args: command line arguments
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)
        self.ipv4_client_started: bool = False
        self._multicast: Multicast = None
        self._firewall: IptablesFirewall = None
        self._nslookup: NSLookup = None

    @property
    def http_proxy(self) -> str:
        """SOCKS5 dante proxy address, e.g http://{proxy_ip}:{proxy_port}/.

        :return: dante proxy address
        :rtype: str
        """
        return self._config.get("http_proxy")

    @property
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT.

        :return: name of the dut interface
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
        """Returns LAN console.

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

    @property
    def nslookup(self) -> NSLookup:
        """Returns NSLookup utility instance.

        :return: nslookup utility instance with console object
        :rtype: NSLookup
        """
        self._nslookup = NSLookup(self._console)
        return self._nslookup

    @hookimpl
    def boardfarm_attached_device_boot(self) -> None:
        """Boardfarm hook implementation to boot LAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        self._add_multicast_to_linux_lan()

    @hookimpl
    async def boardfarm_attached_device_boot_async(self) -> None:
        """Boardfarm hook implementation to boot LAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        await self._connect_async()
        self._add_multicast_to_linux_lan()

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm hook implementation to initialize LAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        self._add_multicast_to_linux_lan()

    @hookimpl
    async def boardfarm_skip_boot_async(self) -> None:
        """Boardfarm hook implementation to initialize LAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        await self._connect_async()
        self._add_multicast_to_linux_lan()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown LAN device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    @hookimpl
    def boardfarm_attached_device_configure(self, config: BoardfarmConfig) -> None:
        """Configure boardfarm attached device.

        :param config: contains both environment and inventory config
        :type config: BoardfarmConfig
        """
        self._setup_static_routes()
        mode = config.get_prov_mode()
        call = {
            "ipv4": self.start_ipv4_lan_client,
            "ipv6": self.start_ipv6_lan_client,
        }
        flag = ["ipv4"] if mode in ["ipv4"] else ["ipv4", "ipv6"]
        for mode in flag:
            call[mode]()

    @hookimpl
    async def boardfarm_attached_device_configure_async(
        self,
        config: BoardfarmConfig,
    ) -> None:
        """Configure boardfarm attached device leveraging asyncio.

        :param config: boardfarm config
        :type config: BoardfarmConfig
        """
        await self._setup_static_routes_async()
        mode = config.get_prov_mode()
        call = {
            "ipv4": self.start_ipv4_lan_client_async,
            "ipv6": self.start_ipv6_lan_client_async,
        }
        flag = ["ipv4"] if mode in ["ipv4"] else ["ipv4", "ipv6"]
        for mode in flag:
            await call[mode]()

    @hookimpl
    def contingency_check(
        self,
        env_req: dict[str, Any],
        device_manager: DeviceManager,
    ) -> None:
        """Make sure the LAN is working fine before use.

        :param env_req: environment request dictionary
        :type env_req: dict[str, Any]
        :param device_manager: device manager instance
        :type device_manager: DeviceManager
        :raises ContingencyCheckError: if LAN console is non responsive
        """
        if (
            self._cmdline_args.skip_contingency_checks
            or get_value_from_dict("lan_clients", env_req) is None
        ):
            return
        _LOGGER.info("Contingency check %s(%s)", self.device_name, self.device_type)
        if "FOO" not in self._console.execute_command("echo FOO"):
            msg = "LAN device console in not responding"
            raise ContingencyCheckError(msg)
        provision_mode = device_manager.get_device_by_type(
            CPE,  # type: ignore[type-abstract]
        ).sw.get_provision_mode()
        if provision_mode in ("ipv4", "dual"):
            self.get_eth_interface_ipv4_address()
        if provision_mode in ("ipv6", "dual"):
            self.get_eth_interface_ipv6_address()

    @property
    def lan_gateway(self) -> str:
        """LAN gateway address.

        :return: LAN gateway address
        :rtype: str
        """
        # TODO: resolve lan gateway address dynamically
        return "192.168.178.1"

    def get_default_gateway(self) -> IPv4Address:
        """Get default gateway from ip route output.

        :return: default gateway ipv4 address
        :rtype: IPv4Address
        """
        out = self._console.execute_command("ip route list 0/0 | awk '{print $3}'")
        try:
            return IPv4Address(out.strip())
        except AddressValueError:
            # Should we just raise an exception instead?
            _LOGGER.warning(
                "Unable to resolve lan client gateway IP. "
                "Using default Ziggo address now. (192.168.178.1)",
            )
            return IPv4Address("192.168.178.1")

    def __kill_dhclient(self, ipv4: bool = True) -> None:
        dhclient_str = f"dhclient {'-4' if ipv4 else '-6'}"

        if ipv4:
            self.release_dhcp(self.iface_dut)
        else:
            self.release_ipv6(self.iface_dut)

        self._console.sendline("ps aux")
        if self._console.expect([dhclient_str, *self._shell_prompt]) == 0:
            _LOGGER.warning(
                "WARN: dhclient still running, something started rogue client!",
            )
            self._console.sendline(
                f"pkill --signal 9 -f {dhclient_str}.*{self.iface_dut}",
            )
            self._console.expect(self._shell_prompt)

        self._console.sendline(f"kill $(</run/dhclient{'' if ipv4 else 6}.pid)")
        self._console.expect(self._shell_prompt)

    async def __kill_dhclient_async(self, ipv4: bool = True) -> None:
        dhclient_str = f"dhclient {'-4' if ipv4 else '-6'}"

        if ipv4:
            await self.release_dhcp_async(self.iface_dut)
        else:
            await self.release_ipv6_async(self.iface_dut)

        self._console.sendline("ps aux")
        if (
            await self._console.expect([dhclient_str, *self._shell_prompt], async_=True)
            == 0
        ):
            _LOGGER.warning(
                "WARN: dhclient still running, something started rogue client!",
            )
            self._console.sendline(
                f"pkill --signal 9 -f {dhclient_str}.*{self.iface_dut}",
            )
            await self._console.expect(self._shell_prompt, async_=True)

        self._console.sendline(f"kill $(</run/dhclient{'' if ipv4 else 6}.pid)")
        await self._console.expect(self._shell_prompt, async_=True)

    def start_ipv4_lan_client(  # noqa: PLR0915
        self,
        wan_gw: str | IPv4Address | None = None,
        prep_iface: bool = False,
    ) -> str:
        """Restart ipv4 dhclient to obtain an IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :type wan_gw: str | IPv4Address | None
        :param prep_iface: restart interface before dhclient request
        :type prep_iface: bool
        :return: IPv4 after renewal
        :rtype: str
        """
        # pylint: disable=too-many-statements
        self.clear_cache()
        ipv4 = None
        self.stop_danteproxy()
        self.check_dut_iface()

        if prep_iface:
            self._console.sendline(
                f"ip link set down {self.iface_dut} && ip link set up {self.iface_dut}",
            )
            self._console.expect(self._shell_prompt)

        if "default" not in self._console.execute_command(
            f"ip route list | grep {self.iface_dut}",
        ):
            self._console.execute_command("ip route flush default")

        self.__kill_dhclient()

        self._console.sendline(f"\nifconfig {self.iface_dut} 0.0.0.0")
        self._console.expect(self._shell_prompt)
        self._console.sendline("rm /var/lib/dhcp/dhclient.leases")
        self._console.expect(self._shell_prompt)
        self._console.sendline(
            "sed -e 's/mv -f $new_resolv_conf $resolv_conf/cat $new_resolv_conf "
            "> $resolv_conf/g' -i /sbin/dhclient-script",
        )
        self._console.expect(self._shell_prompt)
        if self.mgmt_dns is not None:
            self._console.sendline(
                f"sed '/append domain-name-servers {self.mgmt_dns}/d' "
                "-i /etc/dhcp/dhclient.conf",
            )
            self._console.expect(self._shell_prompt)
            self._console.sendline(
                f'echo "append domain-name-servers {self.mgmt_dns};" >> '
                "/etc/dhcp/dhclient.conf",
            )
            self._console.expect(self._shell_prompt)

        self.configure_dhclient_option60(enable=True)
        self.configure_dhclient_option61(enable=True)

        for _ in range(5):
            try:
                self.renew_dhcp(self.iface_dut)
                self.get_interface_ipv4addr(self.iface_dut)
                break
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                self._console.sendcontrol("c")
                self._console.expect(self._shell_prompt)

        self._console.sendline("cat /etc/resolv.conf")
        self._console.expect(self._shell_prompt)
        self._console.sendline(f"ip addr show dev {self.iface_dut}")
        self._console.expect(self._shell_prompt)
        self._console.sendline("ip route")
        # we should verify this so other way, because they could be the same subnets
        # in theory
        i = self._console.expect(
            [
                f"default via {self.lan_gateway} dev {self.iface_dut}",
                pexpect.TIMEOUT,
            ],
            timeout=5,
        )
        if i == 1:
            # update gw
            self._console.sendline("ip route list 0/0 | awk '{print $3}'")
            self._console.expect_exact("ip route list 0/0 | awk '{print $3}'")
            self._console.expect(self._shell_prompt)

            ip_addr = self.get_interface_ipv4addr(self.iface_dut)
            self._console.sendline(f"ip route | grep {ip_addr} | awk '{{print $1}}'")
            self._console.expect_exact(
                f"ip route | grep {ip_addr} | awk '{{print $1}}'",
            )
            self._console.expect(self._shell_prompt)

        if wan_gw is not None and hasattr(self, "lan_fixed_route_to_wan"):
            self._console.sendline(f"ip route add {wan_gw} via {self.lan_gateway}")
            self._console.expect(self._shell_prompt)
        ipv4 = self.get_interface_ipv4addr(self.iface_dut)

        if ipv4:
            self.ipv4_client_started = True
            self.start_danteproxy()

        return ipv4

    async def start_ipv4_lan_client_async(  # noqa: PLR0915
        self,
        wan_gw: str | IPv4Address | None = None,
        prep_iface: bool = False,
    ) -> str:
        """Restart ipv4 dhclient to obtain an IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :type wan_gw: str | IPv4Address | None
        :param prep_iface: restart interface before dhclient request
        :type prep_iface: bool
        :return: IPv4 after renewal
        :rtype: str
        """
        # pylint: disable=too-many-statements
        ipv4 = None
        await self.stop_danteproxy_async()
        await self.check_dut_iface_async()

        if prep_iface:
            self._console.sendline(
                f"ip link set down {self.iface_dut} && ip link set up {self.iface_dut}",
            )
            await self._console.expect(self._shell_prompt, async_=True)

        if "default" not in await self._console.execute_command_async(
            f"ip route list | grep {self.iface_dut}",
        ):
            await self._console.execute_command_async("ip route flush default")

        await self.__kill_dhclient_async()

        self._console.sendline(f"\nifconfig {self.iface_dut} 0.0.0.0")
        await self._console.expect(self._shell_prompt, async_=True)
        self._console.sendline("rm /var/lib/dhcp/dhclient.leases")
        await self._console.expect(self._shell_prompt, async_=True)
        self._console.sendline(
            "sed -e 's/mv -f $new_resolv_conf $resolv_conf/cat $new_resolv_conf "
            "> $resolv_conf/g' -i /sbin/dhclient-script",
        )
        await self._console.expect(self._shell_prompt, async_=True)
        if self.mgmt_dns is not None:
            self._console.sendline(
                f"sed '/append domain-name-servers {self.mgmt_dns}/d' "
                "-i /etc/dhcp/dhclient.conf",
            )
            await self._console.expect(self._shell_prompt, async_=True)
            self._console.sendline(
                f'echo "append domain-name-servers {self.mgmt_dns};" >> '
                "/etc/dhcp/dhclient.conf",
            )
            await self._console.expect(self._shell_prompt, async_=True)

        await self.configure_dhclient_option60_async(enable=True)
        await self.configure_dhclient_option61_async(enable=True)

        for _ in range(5):
            try:
                await self.renew_dhcp_async(self.iface_dut)
                self.get_interface_ipv4addr(self.iface_dut)
                break
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                self._console.sendcontrol("c")
                await self._console.expect(self._shell_prompt, async_=True)

        self._console.sendline("cat /etc/resolv.conf")
        await self._console.expect(self._shell_prompt, async_=True)
        self._console.sendline(f"ip addr show dev {self.iface_dut}")
        await self._console.expect(self._shell_prompt, async_=True)
        self._console.sendline("ip route")
        # we should verify this so other way, because they could be the same subnets
        # in theory
        i = await self._console.expect(
            [
                f"default via {self.lan_gateway} dev {self.iface_dut}",
                pexpect.TIMEOUT,
            ],
            timeout=5,
            async_=True,
        )
        if i == 1:
            # update gw
            self._console.sendline("ip route list 0/0 | awk '{print $3}'")
            await self._console.expect_exact(
                "ip route list 0/0 | awk '{print $3}'",
                async_=True,
            )
            await self._console.expect(self._shell_prompt, async_=True)

            ip_addr = self.get_interface_ipv4addr(self.iface_dut)
            self._console.sendline(f"ip route | grep {ip_addr} | awk '{{print $1}}'")
            await self._console.expect_exact(
                f"ip route | grep {ip_addr} | awk '{{print $1}}'",
                async_=True,
            )
            await self._console.expect(self._shell_prompt, async_=True)

        if wan_gw is not None and hasattr(self, "lan_fixed_route_to_wan"):
            self._console.sendline(f"ip route add {wan_gw} via {self.lan_gateway}")
            await self._console.expect(self._shell_prompt, async_=True)
        ipv4 = self.get_interface_ipv4addr(self.iface_dut)

        if ipv4:
            self.ipv4_client_started = True
            self.start_danteproxy()

        return ipv4

    def start_ipv6_lan_client(
        self,
        wan_gw: str | IPv4Address | None = None,
        prep_iface: bool = False,
    ) -> str:
        """Restart ipv6 dhclient to obtain IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :type wan_gw: str | IPv4Address | None
        :param prep_iface: restart interface before dhclient request
        :type prep_iface: bool
        :return: IPv6 after renewal
        :rtype: str
        """
        ipv6 = None

        self.check_dut_iface()

        if prep_iface:
            self._console.execute_command(
                f"ip link set down {self.iface_dut} && ip link set up {self.iface_dut}",
            )

        self.__kill_dhclient(False)

        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=1",
        )
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.accept_ra=2",
        )
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=0",
        )
        self._console.execute_command(
            f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0",
        )

        # check if board is providing an RA, if yes use that detail to perform DHCPv6
        # default method used will be statefull DHCPv6
        output = self._console.execute_command(
            f"rdisc6 -1 --retry 10 --wait 30000 {self.iface_dut}",
            timeout=400,
        )
        m_bit, o_bit = True, True
        if "Prefix" in output:
            m_bit, o_bit = (
                "Yes" in item for item in re.findall(r"Stateful.*\W", output)
            )

        for _ in range(5):
            try:
                # Condition for Stateless DHCPv6,
                # this should update DNS details via DHCP and IP via SLAAC
                if not m_bit and o_bit:
                    self.renew_ipv6(self.iface_dut, stateless=True)
                elif m_bit and o_bit:
                    self.renew_ipv6(self.iface_dut)
                ipv6 = self.get_interface_ipv6addr(self.iface_dut)
                break
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                self.__kill_dhclient(False)
                self._console.sendcontrol("c")
                self._console.expect(self._shell_prompt)
        if wan_gw is not None and hasattr(self, "lan_fixed_route_to_wan"):
            self._console.execute_command(
                f"ip route add {wan_gw} via {self.lan_gateway}",
            )
        return ipv6

    async def start_ipv6_lan_client_async(
        self,
        wan_gw: str | IPv4Address | None = None,
        prep_iface: bool = False,
    ) -> str:
        """Restart ipv6 dhclient to obtain IP.

        :param wan_gw: WAN gateway IP
            to setup fixed route in case lan_fixed_route_to_wan option is provided
        :type wan_gw: str | IPv4Address | None
        :param prep_iface: restart interface before dhclient request
        :type prep_iface: bool
        :return: IPv6 after renewal
        :rtype: str
        """
        ipv6 = None

        await self.check_dut_iface_async()

        if prep_iface:
            await self._console.execute_command_async(
                f"ip link set down {self.iface_dut} && ip link set up {self.iface_dut}",
            )

        await self.__kill_dhclient_async(False)

        await self._console.execute_command_async(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=1",
        )
        await self._console.execute_command_async(
            f"sysctl net.ipv6.conf.{self.iface_dut}.accept_ra=2",
        )
        await self._console.execute_command_async(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=0",
        )
        await self._console.execute_command_async(
            f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0",
        )

        # check if board is providing an RA, if yes use that detail to perform DHCPv6
        # default method used will be statefull DHCPv6
        output = await self._console.execute_command_async(
            f"rdisc6 -1 --retry 10 --wait 30000 {self.iface_dut}",
            timeout=400,
        )
        m_bit, o_bit = True, True
        if "Prefix" in output:
            m_bit, o_bit = (
                "Yes" in item for item in re.findall(r"Stateful.*\W", output)
            )

        for _ in range(5):
            try:
                # Condition for Stateless DHCPv6,
                # this should update DNS details via DHCP and IP via SLAAC
                if not m_bit and o_bit:
                    await self.renew_ipv6_async(self.iface_dut, stateless=True)
                elif m_bit and o_bit:
                    await self.renew_ipv6_async(self.iface_dut)
                ipv6 = self.get_interface_ipv6addr(self.iface_dut)
                break
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                await self.__kill_dhclient_async(False)
                self._console.sendcontrol("c")
                await self._console.expect(self._shell_prompt, async_=True)
        if wan_gw is not None and hasattr(self, "lan_fixed_route_to_wan"):
            await self._console.execute_command_async(
                f"ip route add {wan_gw} via {self.lan_gateway}",
            )
        return ipv6

    def check_dut_iface(self) -> str:
        """Check that the dut iface exists and has a carrier.

        :return: ip link show command output
        :rtype: str
        :raises BoardfarmException: if iface_dut is not found
        """
        output = self._console.check_output(f"ip link show {self.iface_dut}")
        if (
            self.iface_dut not in output
            or f'Device "{self.iface_dut}" does not exist' in output
        ):
            output = self._console.check_output("ip link")
            msg = f"{self.device_name}: {self.iface_dut} NOT found\n{output}"
            _LOGGER.error(msg)
            raise BoardfarmException(msg)
        if "NO-CARRIER" in output:
            msg = f"{self.device_name}: {self.iface_dut} CARRIER DOWN\n{output}"
            _LOGGER.error(msg)
        return output

    async def check_dut_iface_async(self) -> str:
        """Check that the dut iface exists and has a carrier.

        :return: ip link show command output
        :rtype: str
        :raises BoardfarmException: if iface_dut is not found
        """
        output = await self._console.execute_command_async(
            f"ip link show {self.iface_dut}",
        )
        if (
            self.iface_dut not in output
            or f'Device "{self.iface_dut}" does not exist' in output
        ):
            output = await self._console.execute_command_async("ip link")
            msg = f"{self.device_name}: {self.iface_dut} NOT found\n{output}"
            _LOGGER.error(msg)
            raise BoardfarmException(msg)
        if "NO-CARRIER" in output:
            msg = f"{self.device_name}: {self.iface_dut} CARRIER DOWN\n{output}"
            _LOGGER.error(msg)
        return output

    def configure_dhclient_option60(self, enable: bool) -> None:
        """Configure dhcp server option 60 in dhclient.conf.

        :param enable: add option 60 if True else remove
        :type enable: bool
        """
        if enable:
            out = self._console.check_output(
                "egrep 'vendor-class-identifier' /etc/dhcp/dhclient.conf",
            )
            if re.search("vendor-class-identifier", out) is None:
                self._console.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
                self._console.sendline('send vendor-class-identifier "BFClient";')
                self._console.sendline("EOF")
                self._console.expect(self._shell_prompt)
        else:
            self._console.sendline(
                "sed -i '/vendor-class-identifier/d' /etc/dhcp/dhclient.conf",
            )
            self._console.expect(self._shell_prompt)

    async def configure_dhclient_option60_async(self, enable: bool) -> None:
        """Configure dhcp server option 60 in dhclient.conf.

        :param enable: add option 60 if True else remove
        :type enable: bool
        """
        if enable:
            out = await self._console.execute_command_async(
                "egrep 'vendor-class-identifier' /etc/dhcp/dhclient.conf",
            )
            if re.search("vendor-class-identifier", out) is not None:
                self._console.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
                self._console.sendline('send vendor-class-identifier "BFClient";')
                self._console.sendline("EOF")
                await self._console.expect(self._shell_prompt, async_=True)
        else:
            self._console.sendline(
                "sed -i '/vendor-class-identifier/d' /etc/dhcp/dhclient.conf",
            )
            await self._console.expect(self._shell_prompt, async_=True)

    def configure_dhclient_option61(self, enable: bool) -> None:
        """Configure dhcp server option 61 in dhclient.conf.

        :param enable: add option 61 if True else remove
        :type enable: bool
        """
        if enable:
            mac = self.get_interface_macaddr(self.iface_dut)
            cmd = (
                r"sed -i -e 's/^#\{0,\}send dhcp-client-identifier.*/send "
                rf"dhcp-client-identifier {mac};/' /etc/dhcp/dhclient.conf"
            )
        else:
            cmd = (
                "sed -i -e 's/^send dhcp-client-identifier"
                "/#send dhcp-client-identifier/' /etc/dhcp/dhclient.conf"
            )
        self._console.check_output(cmd)
        self._console.check_output(
            "cat /etc/dhcp/dhclient.conf |grep dhcp-client-identifier",
        )

    async def configure_dhclient_option61_async(self, enable: bool) -> None:
        """Configure dhcp server option 61 in dhclient.conf.

        :param enable: add option 61 if True else remove
        :type enable: bool
        """
        if enable:
            # This shall become ASYNC later.....
            mac = self.get_interface_macaddr(self.iface_dut)
            cmd = (
                r"sed -i -e 's/^#\{0,\}send dhcp-client-identifier.*/send "
                rf"dhcp-client-identifier {mac};/' /etc/dhcp/dhclient.conf"
            )
        else:
            cmd = (
                "sed -i -e 's/^send dhcp-client-identifier"
                "/#send dhcp-client-identifier/' /etc/dhcp/dhclient.conf"
            )
        await self._console.execute_command_async(cmd)
        await self._console.execute_command_async(
            "cat /etc/dhcp/dhclient.conf |grep dhcp-client-identifier",
        )

    def configure_dhclient_option125(self, enable: bool) -> None:
        """Configure dhcp server option 125 in dhclient.conf.

        :param enable: add option 125 if True else remove
        :type enable: bool
        """
        if not enable:
            self._console.sendline(
                "sed -i -e 's|request option-125,|request |' /etc/dhcp/dhclient.conf",
            )
            self._console.expect(self._shell_prompt)
            self._console.sendline("sed -i '/option-125/d' /etc/dhcp/dhclient.conf")
            self._console.expect(self._shell_prompt)
        else:
            out = self._console.check_output(
                "egrep 'request option-125' /etc/dhcp/dhclient.conf",
            )
            if re.search("request option-125,", out) is None:
                self._console.sendline(
                    "sed -i -e 's|request |\\n"
                    "option option-125 code 125 = string;\\n\\n"
                    "request option-125, |' /etc/dhcp/dhclient.conf",
                )
                self._console.expect(self._shell_prompt)
                # details of Text for HexaDecimal value as
                # Enterprise code (3561) 00:00:0D:E9 length  (22)16
                # code 01  length 06  (BFVER0) 42:46:56:45:52:30
                # code 03  length 06  (BFCLAN)  42:46:43:4c:41:4e
                mac = self.get_interface_macaddr(self.iface_dut)
                value = "VAAU" + "".join(mac.split(":")[0:4]).upper()
                encoded_name = str.encode(value)
                hex_name = iter(binascii.hexlify(encoded_name).decode("utf-8"))
                code_02 = ":".join([f"{j}{k}" for j, k in zip(hex_name, hex_name)])
                len_02 = hex(len(value)).replace("0x", "").zfill(2)
                total_len = hex(18 + len(value)).replace("0x", "").zfill(2)
                option_125 = (
                    f"00:00:0D:E9:{total_len}:01:06:44:38:42:36:42:37:02:"
                    f"{len_02}:{code_02}:03:06:42:46:43:4c:41:4e"
                )
                self._console.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
                self._console.sendline(f"send option-125 = {option_125};")
                self._console.sendline("")
                self._console.sendline("EOF")
                self._console.expect(self._shell_prompt)

    def configure_dhcpv6_option17(self, enable: bool) -> None:
        """Configure LAN identity DHCPv6 option 17.

        :param enable: Add dhcpv6 option 17 if True else remove
        :type enable: bool
        """
        if not enable:
            self._console.sendline(
                "sed -i -e 's|ntp-servers, dhcp6.vendor-opts|ntp-servers|' "
                "/etc/dhcp/dhclient.conf",
            )
            self._console.expect(self._shell_prompt)
            self._console.sendline(
                "sed -i '/dhcp6.vendor-opts/d' /etc/dhcp/dhclient.conf",
            )
            self._console.expect(self._shell_prompt)
        else:
            out = self._console.check_output(
                "egrep 'dhcp6.vendor-opts' /etc/dhcp/dhclient.conf",
            )
            if re.search("request dhcp6.vendor-opts,", out) is None:
                self._console.sendline(
                    "sed -i -e 's|ntp-servers;|ntp-servers, "
                    "dhcp6.vendor-opts; |' /etc/dhcp/dhclient.conf",
                )
                self._console.expect(self._shell_prompt)
                # Enterprise code (3561) 00:00:0D:E9
                # code 11  length 06  (BFVER0) 42:46:56:45:52:30
                # code 13  length 06  (BFCLAN)  42:46:43:4c:41:4e
                encoded_name = str.encode(self.device_name)
                hex_name = iter(binascii.hexlify(encoded_name).decode("utf-8"))
                code_12 = ":".join([f"{j}{k}" for j, k in zip(hex_name, hex_name)])
                len_12 = hex(len(self.device_name)).replace("0x", "").zfill(2)
                option_17 = (
                    "00:00:0D:E9:00:0b:00:06:42:46:56:45:52:30:00:0c:00:"
                    f"{len_12}:{code_12}:00:0d:00:06:42:46:43:4c:41:4e"
                )
                self._console.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
                self._console.sendline(f"send dhcp6.vendor-opts {option_17};")
                self._console.sendline("")
                self._console.sendline("EOF")
                self._console.expect(self._shell_prompt)

    def enable_ipv6(self) -> None:
        """Enable ipv6 on the connected client interface."""
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.accept_ra=2",
        )
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=0",
        )

    def disable_ipv6(self) -> None:
        """Disable ipv6 on the connected client interface."""
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=1",
        )
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=1",
        )

    def create_upnp_rule(
        self,
        int_port: str,
        ext_port: str,
        protocol: str,
        url: str,
    ) -> str:
        """Create UPnP rule on the device.

        :param int_port: internal port for upnp
        :type int_port: str
        :param ext_port: external port for upnp
        :type ext_port: str
        :param protocol: protocol to be used
        :type protocol: str
        :param url: url to be used
        :type url: str
        :return: output of upnpc add port command
        :rtype: str
        """
        ip_addr = self.get_interface_ipv4addr(self.iface_dut)
        return self._console.execute_command(
            f"upnpc -u {url} -m {self.iface_dut} -a {ip_addr} {int_port} {ext_port} {protocol}",
        )

    def _add_multicast_to_linux_lan(self) -> None:
        self._multicast = Multicast(
            self.device_name,
            self.iface_dut,
            self._console,
            self._shell_prompt,
        )

    def delete_upnp_rule(self, ext_port: str, protocol: str, url: str) -> str:
        """Delete UPnP rule on the device.

        :param ext_port: external port for upnp
        :type ext_port: str
        :param protocol: protocol to be used
        :type protocol: str
        :param url: url to be used
        :type url: str
        :return: output of upnpc delete port command
        :rtype: str
        """
        return self._console.execute_command(
            f"upnpc -u {url} -m {self.iface_dut} -d {ext_port} {protocol}"
        )

    def netcat(self, host_ip: str, port: str, additional_args: str) -> None:
        """Run netcat command to initiate brute force.

        :param host_ip: host ip address
        :type host_ip: str
        :param port: port number of the host
        :type port: str
        :param additional_args: additional args to be provided with netcat command
        :type additional_args: str
        :raises NotImplementedError: yet to be implemented
        """
        raise NotImplementedError

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
            return ifconfig_data[0]["mtu"]  # type: ignore[index]
        msg = f"ifconfig {interface} is not available"
        raise ValueError(msg)

    def get_hostname(self) -> str:
        """Get the hostname of the device.

        :return: hostname of the device
        :rtype: str
        """
        return self.hostname()

    def _update_file_entry(self, hosts_data: list) -> None:
        self._console.sendline("cat > /etc/hosts << EOF")
        for line in hosts_data:
            self._console.sendline(line)
        self._console.sendline("EOF")
        self._console.expect(self._shell_prompt)

    def add_hosts_entry(self, ip: str, host_name: str) -> None:
        """Add entry in hosts file.

        :param ip: host ip addr
        :type ip: str
        :param host_name: host name to be added
        :type host_name: str
        """
        hosts = self._console.execute_command("cat /etc/hosts")
        hosts_data = hosts.splitlines()
        hosts_data.append(f"{ip}    {host_name}")
        self._update_file_entry(hosts_data=hosts_data)

    def delete_hosts_entry(self, host_name: str, ip: str) -> None:
        """Delete entry in hosts file.

        :param host_name: host name to be deleted
        :type host_name: str
        :param ip: host ip addr
        :type ip: str
        """
        hosts = self._console.execute_command("cat /etc/hosts")
        hosts_data = [
            line
            for line in hosts.splitlines()
            if f"{host_name}{ip}" not in line.replace(" ", "")
        ]
        self._update_file_entry(hosts_data=hosts_data)

    def flush_arp_cache(self) -> None:
        """Flushes arp cache entries."""
        self._console.execute_command("ip neigh flush all")

    def get_arp_table(self) -> str:
        """Fetch ARP table output.

        :return: output of arp command
        :rtype: str
        """
        return self._console.execute_command("arp -n")

    def delete_arp_table_entry(self, ip: str, intf: str) -> None:
        """Delete ARP table entry.

        :param ip: ip of the host entry to be deleted
        :type ip: str
        :param intf: interface for which the entry needs to be deleted
        :type intf: str
        """
        self._console.execute_command(f"ip neigh del {ip} dev {intf}")


if __name__ == "__main__":
    # stubbed instantation of the device
    # this would throw a linting issue in case the device does not follow the template
    LinuxLAN(config={}, cmdline_args=Namespace())
