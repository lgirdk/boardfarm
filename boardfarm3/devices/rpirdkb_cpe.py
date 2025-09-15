"""X86EMLTRBB_rdk based CPE device class."""

from __future__ import annotations

import logging
from functools import cached_property
from ipaddress import AddressValueError, IPv4Address
from time import sleep
from typing import TYPE_CHECKING, Any

import jc
import pexpect

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.exceptions import (
    BoardfarmException,
    ConfigurationFailure,
    DeviceBootFailure,
    NotSupportedError,
)
from boardfarm3.lib.connection_factory import connection_factory
from boardfarm3.lib.cpe_sw import CPESwLibraries
from boardfarm3.lib.power import get_pdu
from boardfarm3.lib.utils import retry_on_exception
from boardfarm3.templates.acs import ACS
from boardfarm3.templates.cpe import CPE, CPEHW
from boardfarm3.templates.provisioner import Provisioner

if TYPE_CHECKING:
    from argparse import Namespace

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.device_manager import DeviceManager
    from boardfarm3.lib.hal.cpe_wifi import WiFiHal
    from boardfarm3.templates.cpe.cpe_hw import TerminationSystem
    from boardfarm3.templates.tftp import TFTP

_LOGGER = logging.getLogger(__name__)


class RPiRDKBHW(CPEHW):
    """RPiRDKB Arm hardware device class."""

    def __init__(self, config: dict[str, Any], cmdline_args: Namespace) -> None:
        """Initialize CPE hardware.

        :param config: CPE config
        :param cmdline_args: command line arguments
        """
        self._config = config
        self._cmdline_args = cmdline_args
        self._console: BoardfarmPexpect = None

    @property
    def config(self) -> dict[str, Any]:
        """Device config.

        :return: Device config
        :rtype: dict[str, Any]
        """
        return self._config

    @cached_property
    def mac_address(self) -> str:
        """Get CPE MAC address.

        From either the inventory or (if not provided) the RPi itself.

        :raises ValueError: if the mac is not provided/found
        :return: MAC address
        :rtype: str
        """
        if mac := self._config.get("mac"):
            return mac
        if self._console:
            return self._console.execute_command(
                "cat `find /sys/devices/ -type d -name erouter0`/address"
            )
        msg = "Failed to get mac address"
        raise ValueError(msg)

    @cached_property
    def serial_number(self) -> str:
        """Get CPE Serial number.

        :return: MAC address
        :rtype: str
        """
        if self._console:
            return self._console.execute_command(
                "grep Serial /proc/cpuinfo |awk '{print $3}'",
            )
        return self._config.get("serial")

    @property
    def wan_iface(self) -> str:
        """WAN interface name.

        :return: the wan interface name
        :rtype: str
        """
        return "erouter0"

    @property
    def mta_iface(self) -> str:
        """MTA interface name.

        :raises NotSupportedError: voice is not enabled for container
        """
        raise NotSupportedError

    @property
    def _shell_prompt(self) -> list[str]:
        """Console prompt.

        :return: the shell prompt
        :rtype: list[str]
        """
        return [r"root@RaspberryPi-Gateway:.*#"]

    def connect_to_consoles(self, device_name: str) -> None:
        """Establish connection to the device console.

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
        self._console.login_to_server()
        try:
            # on connection the serial console can be very dirty
            self._console.sendline("")
            self._console.expect(r".+", 3)
        except pexpect.TIMEOUT:
            pass

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

    def disconnect_from_consoles(self) -> None:
        """Disconnect/Close the console connections."""
        if self._console is not None:
            self._console.close()

    def get_interactive_consoles(self) -> dict[str, BoardfarmPexpect]:
        """Get interactive consoles of the device.

        :returns: device interactive consoles
        """
        return {"console": self._console}

    def power_cycle(self) -> None:
        """Power cycle the CPE via cli.

        :raises BoardfarmException: on PDU power cycle failure
        """
        if not get_pdu(self._config.get("powerport")).power_cycle():
            msg = "Failed to power cylce CPE via PDU"
            raise BoardfarmException(msg)
        self._console.expect("Booting Linux on physical CPU")
        self._console.expect("automatic login")

    def flash_via_bootloader(
        self,
        image: str,  # noqa: ARG002
        tftp_devices: dict[str, TFTP],  # noqa: ARG002
        termination_sys: TerminationSystem = None,  # noqa: ARG002
        method: str | None = None,  # noqa: ARG002
    ) -> None:
        """Flash cpe via the bootloader.

        :param image: image name
        :type image: str
        :param tftp_devices: a list of LAN side TFTP devices
        :type tftp_devices: dict[str, TFTP]
        :param termination_sys: the termination system device (e.g. CMTS),
            defaults to None
        :type termination_sys: TerminationSystem
        :param method: flash method, defaults to None
        :type method: str, optional
        :raises NotSupportedError: docker container cannot be flashed
        """
        raise NotSupportedError

    def wait_for_hw_boot(self) -> None:
        """Wait for CPE to have WAN interface added.

        :raises DeviceBootFailure: if CPE is unable to bring up WAN interface
        """
        for _ in range(20):
            if self.wan_iface in self._console.execute_command("ip a"):
                break
            sleep(5)
        else:
            msg = f"CPE failed to bring up WAN interface: {self.wan_iface}"
            raise DeviceBootFailure(msg)


class RPiRDKBSW(CPESwLibraries):  # pylint: disable=R0904
    """RPiRDKB software component device class."""

    _hw: RPiRDKBHW
    _use_oui = False

    def __init__(self, hardware: RPiRDKBHW) -> None:
        """Initialise the RPiRDKB sofware class.

        :param hardware: the board hw object
        :type hardware: RPiRDKBHW
        """
        super().__init__(hardware)

    def _set_up_terminal(self) -> None:
        # use sparingly
        self._console.execute_command("stty columns 200; export TERM=xterm")

    @property
    def wifi(self) -> WiFiHal:
        """Return instance of WiFi component of RPiRDKB software.

        :raises NotSupportedError: WiFi is not enabled on container...yet!!
        """
        raise NotSupportedError

    @property
    def version(self) -> str:
        """CPE software version.

        This will reload after each flash.
        :return: version
        :rtype: str
        """
        return self._console.execute_command("cat /etc/version")

    @property
    def erouter_iface(self) -> str:
        """E-Router interface name.

        :return: E-Router interface name
        :rtype: str
        """
        return "erouter0"

    @property
    def lan_iface(self) -> str:
        """LAN interface name.

        :return: LAN interface name
        :rtype: str
        """
        return "brlan0"

    @property
    def guest_iface(self) -> str:
        """Guest network interface name.

        :return: name of the guest network interface
        :rtype: str
        """
        return "br-guest"

    @property
    def json_values(self) -> dict[str, Any]:
        """CPE Specific JSON values.

        :return: the CPE Specific JSON values
        :rtype: dict[str, Any]
        """
        json: dict[str, str] = {}

        # Return the default UCI output
        uci_output = self._console.execute_command("uci show").splitlines()
        for line in uci_output:
            if "=" in line:
                k, v = line.strip().split("=")
                json[k] = v
        return json

    @property
    def gui_password(self) -> str:
        """GUI login password.

        :return: GUI password
        :rtype: str
        """
        return self._hw.config.get("gui_password", "admin")

    @cached_property
    def cpe_id(self) -> str:
        """TR069 CPE ID.

        :return: CPE ID
        :rtype: str
        """
        if not self._use_oui:
            return self._hw.serial_number
        val = retry_on_exception(
            method=self.dmcli.GPV,
            args=("Device.DeviceInfo.ManufacturerOUI",),
        )
        oui = val.rval
        val = retry_on_exception(
            method=self.dmcli.GPV,
            args=("Device.DeviceInfo.ProductClass",),
        )
        prod_class = val.rval
        return f"{oui}-{prod_class}-{self._hw.serial_number}"

    @property
    def tr69_cpe_id(self) -> str:
        """TR-69 CPE Identifier.

        :return: TR069 CPE ID
        :rtype: str
        """
        return self.cpe_id

    @property
    def lan_gateway_ipv4(self) -> IPv4Address:
        """LAN Gateway IPv4 address.

        :return: the ip (if present) 255.255.255.255 otherwise
        :rtype: IPv4Address
        """
        try:
            return IPv4Address(
                self._console.execute_command(
                    f"ifconfig {self.lan_iface}|grep 'inet addr:' |"
                    " tr ':' ' '| awk '{print $3}'"
                )
            )

        except AddressValueError:
            return IPv4Address("255.255.255.255")

    def is_production(self) -> bool:
        """Is production software.

        Production software has limited capabilities.
        :return: Production status
        :rtype: bool
        """
        return False

    def reset(self, method: str | None = None) -> None:  # noqa: ARG002
        """Perform a reset via given method.

        :param method: reset method(sw/hw)
        """
        self._hw.power_cycle()

    def factory_reset(self, method: str | None = None) -> bool:  # noqa: ARG002
        """Perform factory reset CPE via given method.

        :param method: factory reset method. Default None.
        :type method: str | None
        :return: True (legacy API)
        :rtype: bool
        """
        self._set_up_terminal()
        self.dmcli.SPV(
            "Device.X_CISCO_COM_DeviceControl.FactoryReset",
            "Router,Wifi,Firewall",
        )
        self._console.expect("Booting Linux on physical CPU")
        self._console.expect("automatic login")
        return True

    def wait_for_boot(self) -> None:
        """Wait for CPE to boot."""
        self._hw.wait_for_hw_boot()

    def get_provision_mode(self) -> str:
        """Return provision mode.

        :return: the provisioning mode
        :rtype: str
        """
        return self._hw.config.get("eRouter_Provisioning_mode", "dual")

    def verify_cpe_is_booting(self) -> None:
        """Verify CPE is booting.

        :raises NotSupportedError: containers don't have a booting stage
        """
        raise NotSupportedError

    def wait_device_online(self) -> None:
        """Wait for WAN interface to come online.

        :raises DeviceBootFailure: if board is not online
        """
        self._set_up_terminal()
        for _ in range(20):
            if retry_on_exception(self.is_online, ()):
                return
            sleep(20)
        msg = "Board not online"
        raise DeviceBootFailure(msg)

    def configure_management_server(self, url: str) -> None:
        """Re-enable CWMP service after updating Management Server URL.

        Optionally can also reconfigure the username and password.

        :param url: Management Server URL
        :type url: str
        """
        retry_on_exception(
            self.dmcli.SPV,
            ("Device.ManagementServer.URL", url),
        )
        retry_on_exception(
            self.dmcli.SPV,
            ("Device.ManagementServer.PeriodicInformInterval", "10", "uint"),
        )
        retry_on_exception(
            self.dmcli.SPV,
            ("Device.ManagementServer.EnableCWMP", "false", "bool"),
        )
        retry_on_exception(
            self.dmcli.SPV,
            ("Device.ManagementServer.EnableCWMP", "true", "bool"),
        )
        if "7547" not in url:  # Not GenieACS, a bit dirty, revisit
            self._use_oui = False

    def finalize_boot(self) -> bool:
        """Validate board settings post boot.

        :raises NotImplementedError: device does not have a finalize stage
        """
        raise NotImplementedError

    @property
    def aftr_iface(self) -> str:
        """AFTR interface name.

        :raises NotImplementedError: device does not have an AFTR IFACE
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


class RPiRDKBCPE(CPE, BoardfarmDevice):
    """RPiRDKB device class for an RPi4 RDKB device ."""

    def __init__(self, config: dict[str, Any], cmdline_args: Namespace) -> None:
        """Initialize RPiRDKB CPE container.

        :param config: configuration from inventory
        :type config: Dict
        :param cmdline_args: command line args
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)

        self._hw: RPiRDKBHW = RPiRDKBHW(config, cmdline_args)
        self._sw: RPiRDKBSW = None

    @property
    def config(self) -> dict:
        """Get device configuration.

        :returns: device configuration
        """
        return self._config

    @property
    def hw(self) -> RPiRDKBHW:
        """The RPiRDKB Hardware class object.

        :return: object holding hardware component details.
        :rtype: RPiRDKBHW
        """
        return self._hw

    @property
    def sw(self) -> RPiRDKBSW:
        """The RPiRDKB Software class object.

        :return: object holding software component details.
        :rtype: RPiRDKBSW
        """
        return self._sw

    @hookimpl
    def boardfarm_device_boot(self, device_manager: DeviceManager) -> None:
        """Boardfarm hook implementation to boot the ETTH device.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        """
        self.hw.connect_to_consoles(self.device_name)
        self._sw = RPiRDKBSW(self._hw)
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
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
        self._sw = RPiRDKBSW(self._hw)
        self.hw.power_cycle()
        self.hw.wait_for_hw_boot()
        # let the console settle
        if self.config.get("software") and self.config.get("software").get(
            "factory_reset"
        ):
            sleep(60)
            self.sw.factory_reset()
        self.sw.wait_device_online()

        # This part is kept since it is missing
        # implementation to add ACS URL from DHCP vendor options
        if acs := device_manager.get_device_by_type(
            ACS,  # type: ignore[type-abstract]
        ):
            acs_url = acs.config.get("acs_mib")  # type: ignore[attr-defined]
            self.sw.configure_management_server(url=acs_url)
        _LOGGER.info("TR069 CPE IP: %s", self.sw.cpe_id)

    def _is_http_gui_running(self) -> bool:
        return bool(
            self.hw.get_console("console").execute_command(
                "netstat -nlp |grep ':::80'",
            )
        )

    @hookimpl
    def boardfarm_device_configure(self) -> None:
        """Configure boardfarm device.

        :raises ConfigurationFailure: if the http service cannot be run
        """
        if not self._is_http_gui_running():
            msg = "http daemon failed to start"
            raise ConfigurationFailure(msg)
        retry_on_exception(
            method=self.sw.dmcli.SPV,
            args=("Device.Users.User.3.Password", "bigfoot1", "string"),
        )
        console = self.hw.get_console("console")
        retry_on_exception(
            console.execute_command,
            ("ip link set eth0 master brlan0", 5),
        )
        retry_on_exception(
            console.execute_command,
            ("ifconfig eth0 up", 5),
        )

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown the ETTH device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self.hw.disconnect_from_consoles()

    @hookimpl(tryfirst=True)
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm skip boot hook implementation."""
        _LOGGER.info(
            "Initializing %s(%s) device with skip-boot option",
            self.device_name,
            self.device_type,
        )
        self._hw.connect_to_consoles(self.device_name)
        self._sw = RPiRDKBSW(self._hw)

    def get_interactive_consoles(self) -> dict[str, BoardfarmPexpect]:
        """Get interactive consoles of the device.

        :return: device interactive consoles
        :rtype: dict[str, BoardfarmPexpect]
        """
        return self.hw.get_interactive_consoles()
