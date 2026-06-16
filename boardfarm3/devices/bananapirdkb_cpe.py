"""Banana Pi running RDKB."""

from __future__ import annotations

import contextlib
import logging
import time
from functools import cached_property
from typing import TYPE_CHECKING, Any

import pexpect

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.devices.rpirdkb_cpe import RPiRDKBCPE, RPiRDKBHW, RPiRDKBSW
from boardfarm3.exceptions import DeviceBootFailure
from boardfarm3.lib.connection_factory import connection_factory
from boardfarm3.templates.acs import ACS
from boardfarm3.templates.core_router import CoreRouter
from boardfarm3.templates.provisioner import Provisioner

if TYPE_CHECKING:
    from argparse import Namespace

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)


class BananaPiRDKBHW(RPiRDKBHW):
    """The BananaPi HW class."""

    @property
    def _shell_prompt(self) -> list[str]:
        """Console prompt.

        :return: the shell prompt
        :rtype: list[str]
        """
        return [r"root@Filogic-GW:.*#"]

    def connect_to_consoles(self, device_name: str) -> None:
        """Establish connection to the device console.

        Handles the LXC console detach banner and login prompt that appear
        when attaching via ``lxc console``.

        :param device_name: device name
        :type device_name: str
        """
        self._console = connection_factory(
            connection_type=str(self._config.get("connection_type")),
            connection_name=f"{device_name}.console",
            conn_command=self._config["conn_cmd"][0],
            save_console_logs=self._cmdline_args.save_console_logs,
            shell_prompt=self._shell_prompt,
        )
        # Consume the lxc console detach banner if present
        with contextlib.suppress(pexpect.TIMEOUT):
            self._console.expect(r"To detach from the console", timeout=5)
        # Send a newline to surface the login or shell prompt
        self._console.sendline("")
        idx = self._console.expect(
            [r"Filogic-GW login:", *self._shell_prompt],
            timeout=10,
        )
        if idx == 0:
            # Autologin is not active on the LXC console device
            self._console.sendline("root")
            self._console.expect(self._shell_prompt)

    def power_cycle(self) -> None:
        """Power cycle the device.

        If ``powerport`` is present in the inventory config the PDU path is
        used (delegates to the parent class); the console connection remains
        open and its identity is unchanged.

        Otherwise a ``reboot`` command is issued on the active console.
        Because the console session runs over SSH (``lxc console``), the
        connection terminates when the container restarts.  The resulting EOF
        is swallowed, the dead connection is closed, and the SSH session is
        re-established by retrying :meth:connect_to_consoles until the
        login prompt reappears (up to 120 s).

        :raises DeviceBootFailure: if the console-reboot path is taken and
            the container does not present a login prompt within 120 s
        """
        if self._config.get("powerport"):
            super().power_cycle()
            return

        self._console.sendline("reboot")
        idx = self._console.expect(
            [pexpect.EOF, r"Filogic-GW login:"],
            timeout=120,
        )
        if idx == 1:
            # Serial/physical: connection survived the reboot — just log back in
            self._console.sendline("root")
            self._console.expect(self._shell_prompt)
            return

        # idx == 0: SSH session dropped (virtual / LXC over SSH) — reconnect
        self.disconnect_from_consoles()
        device_name = str(self._config.get("name", "board"))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            with contextlib.suppress(pexpect.EOF, pexpect.TIMEOUT):
                self.connect_to_consoles(device_name)
                return
            self.disconnect_from_consoles()  # type: ignore[unreachable]
            time.sleep(5)
        msg = f"{device_name}: container did not come back up within 120 s after reboot"
        raise DeviceBootFailure(msg)

    def get_console(self, console_name: str) -> BoardfarmPexpect:
        """Return console instance with the given name.

        :param console_name: name of the console
        :type console_name: str
        :raises ValueError: on unknown console name
        :return: console instance with given name
        :rtype: BoardfarmPexpect
        """
        if console_name == "console":
            return self._console
        msg = f"Unknown console name: {console_name}"
        raise ValueError(msg)


class BananaPiRDKBSW(RPiRDKBSW):  # pylint: disable=R0904
    """The BananaPi SW class."""

    _hw: BananaPiRDKBHW

    def __init__(self, hardware: BananaPiRDKBHW) -> None:
        """Initialise the BananaPi software class.

        :param hardware: the board hw object
        :type hardware: BananaPiRDKBHW
        """
        super().__init__(hardware)

    @cached_property
    def tr69_cpe_id(self) -> str:
        """TR-69 CPE Identifier read from the device via dmcli.

        :return: serial number as reported by Device.DeviceInfo.SerialNumber
        :rtype: str
        """
        return self.dmcli.GPV("Device.DeviceInfo.SerialNumber").rval


class BananaPiRDKBCPE(RPiRDKBCPE, BoardfarmDevice):
    """The BananaPi CPE class."""

    def __init__(self, config: dict[str, Any], cmdline_args: Namespace) -> None:
        """Initialize BananaPi CPE container.

        :param config: configuration from inventory
        :type config: dict[str, Any]
        :param cmdline_args: command line args
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)
        self._hw: BananaPiRDKBHW = BananaPiRDKBHW(config, cmdline_args)

    @property
    def hw(self) -> BananaPiRDKBHW:
        """The BananaPi Hardware class object.

        :return: object holding hardware component details.
        :rtype: BananaPiRDKBHW
        """
        return self._hw

    @property
    def sw(self) -> BananaPiRDKBSW:
        """The BananaPi Software class object.

        :return: object holding software component details.
        :rtype: BananaPiRDKBSW
        """
        return self._sw  # type: ignore[return-value]

    def _prep_device(self, device_manager: DeviceManager) -> None:
        """Configure the management server after a reboot.

        Adds missing IPv4/IPv6 default routes via the router's DUT-facing
        interface, sets the ACS URL and periodic interval, then toggles
        CWMP to trigger an immediate inform.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        """
        # pylint: disable=line-too-long
        acs = next(iter(device_manager.get_devices_by_type(ACS).values()))  # type: ignore[type-abstract]
        router = next(iter(device_manager.get_devices_by_type(CoreRouter).values()))  # type: ignore[type-abstract]
        # pylint: enable=line-too-long
        console = self._hw.get_console("console")

        ipv4_hop = router.get_interface_ipv4addr(router.iface_dut)
        if "default" not in console.execute_command("ip -4 route show default"):
            console.execute_command(f"ip route add default via {ipv4_hop}")

        ipv6_hop = router.get_interface_ipv6addr(router.iface_dut)
        if "default" not in console.execute_command("ip -6 route show default"):
            console.execute_command(f"ip -6 route add default via {ipv6_hop}")

        self._sw.dmcli.SPV(
            param="Device.ManagementServer.EnableCWMP",
            value="false",
            type_set="bool",
        )
        self._sw.dmcli.SPV(
            param="Device.ManagementServer.URL",
            value=acs.config["acs_mib"],  # type: ignore[attr-defined]
        )
        self._sw.dmcli.SPV(
            param="Device.ManagementServer.PeriodicInformInterval",
            value="10",
            type_set="uint",
        )
        self._sw.dmcli.SPV(
            param="Device.ManagementServer.EnableCWMP",
            value="true",
            type_set="bool",
        )

    @hookimpl
    def boardfarm_device_boot(self, device_manager: DeviceManager) -> None:
        """Boardfarm hook implementation to boot the BananaPi device.

        Connects to the console, provisions DHCP, reboots the container,
        waits for erouter0 to come up and receive an IP, then configures
        the management server so the CPE registers with GenieACS.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        """
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._hw.connect_to_consoles(self.device_name)
        self._sw = BananaPiRDKBSW(self._hw)
        if provisioner := device_manager.get_device_by_type(
            Provisioner,  # type: ignore[type-abstract]
        ):
            provisioner.provision_cpe(
                cpe_mac=self.hw.mac_address, dhcpv4_options={}, dhcpv6_options={}
            )
        else:
            _LOGGER.warning(
                "Skipping CPE provisioning. Provisioner for %s(%s) not found!",
                self.device_name,
                self.device_type,
            )
        console_before = self._hw.get_console("console")
        self.hw.power_cycle()
        if self._hw.get_console("console") is not console_before:
            self._sw = BananaPiRDKBSW(self._hw)
        self.hw.wait_for_hw_boot()
        self.sw.wait_device_online()
        if device_manager.get_device_by_type(
            ACS,  # type: ignore[type-abstract]
        ):
            self._prep_device(device_manager)
        _LOGGER.info("TR069 CPE ID: %s", self.sw.cpe_id)

    @hookimpl(tryfirst=True)
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm skip boot hook implementation."""
        _LOGGER.info(
            "Initializing %s(%s) device with skip-boot option",
            self.device_name,
            self.device_type,
        )
        self._hw.connect_to_consoles(self.device_name)
        self._sw = BananaPiRDKBSW(self._hw)

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown the BananaPi device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self.hw.disconnect_from_consoles()
