"""Prpl OS based CPE device class."""

from __future__ import annotations

import logging
import re
from functools import cached_property
from ipaddress import AddressValueError, IPv4Address
from time import sleep
from typing import TYPE_CHECKING, Any

import jc

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.exceptions import (
    ConfigurationFailure,
    DeviceBootFailure,
    NotSupportedError,
)
from boardfarm3.lib.connection_factory import connection_factory
from boardfarm3.lib.cpe_sw import CPESwLibraries
from boardfarm3.lib.utils import retry
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


# pylint: disable=duplicate-code
class PrplOSx86HW(CPEHW):
    """PrplOS x86 hardware device class."""

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

    @property
    def mac_address(self) -> str:
        """Get CPE MAC address.

        :return: MAC address
        :rtype: str
        """
        if self._console:
            output = self._console.execute_command("grep HWMACADDRESS /etc/environment")
            return re.findall('"([^"]*)"', output).pop()

        return self._config.get("mac")

    @property
    def serial_number(self) -> str:
        """Get CPE Serial number.

        :return: MAC address
        :rtype: str
        """
        if self._console:
            output = self._console.execute_command("grep SERIALNUMBER /etc/environment")
            return re.findall('"([^"]*)"', output).pop()

        return self._config.get("serial")

    @property
    def wan_iface(self) -> str:
        """WAN interface name.

        :return: the wan interface name
        :rtype: str
        """
        return "eth1"

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
        return [r"/[a-zA-Z]* #"]

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
        """Power cycle the CPE via cli."""
        self._console.execute_command("reboot -f -d 5")
        # sleep for 10s before container restarts
        sleep(10)
        self.disconnect_from_consoles()
        self.connect_to_consoles("board")

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


class PrplOSSW(CPESwLibraries):  # pylint: disable=R0904
    """PrplOS software component device class."""

    _hw: PrplOSx86HW

    def __init__(self, hardware: PrplOSx86HW) -> None:
        """Initialise the PrplOS sofware class.

        :param hardware: the board hw object
        :type hardware: PrplOSx86HW
        """
        super().__init__(hardware)

    @property
    def wifi(self) -> WiFiHal:
        """Return instance of WiFi component of PrplOS software.

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
        return self._console.execute_command("cat /etc/build.prplos.version")

    @property
    def erouter_iface(self) -> str:
        """E-Router interface name.

        :return: E-Router interface name
        :rtype: str
        """
        return "eth1"

    @property
    def lan_iface(self) -> str:
        """LAN interface name.

        :return: LAN interface name
        :rtype: str
        """
        return "br-lan"

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
        console = self._get_console("default_shell")
        serial = re.findall(
            '"([^"]*)"',
            console.execute_command("grep SERIALNUMBER /etc/environment"),
        ).pop()
        oui = re.findall(
            '"([^"]*)"',
            console.execute_command("grep MANUFACTUREROUI /etc/environment"),
        ).pop()
        return f"{oui}-{serial}"

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
        console = self._get_console("default_shell")
        try:
            return IPv4Address(
                console.execute_command(
                    "ifconfig br-lan|grep 'inet addr:' | tr ':' ' '| awk '{print $3}'"
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
        :raises NotSupportedError: Factory reset not supported on containers.
        """
        raise NotSupportedError

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
        for _ in range(20):
            if self.is_online():
                return
            sleep(20)
        msg = "Board not online"
        raise DeviceBootFailure(msg)

    def configure_management_server(
        self, url: str, username: str | None = "", password: str | None = ""
    ) -> None:
        """Re-enable CWMP service after updating Management Server URL.

        Optionally can also reconfigure the username and password.

        :param url: Management Server URL
        :type url: str
        :param username: CWMP client username, defaults to ""
        :type username: str | None, optional
        :param password: CWMP client password, defaults to ""
        :type password: str | None, optional
        """
        console = self._get_console("default_shell")
        console.sendline("ubus-cli")
        console.expect(" > ")
        console.sendline(f'Device.ManagementServer.URL="{url}"')
        console.expect(" > ")
        console.sendline(f'Device.ManagementServer.Username="{username}"')
        console.expect(" > ")
        if password:  # setting password is not mandatory!
            console.sendline(f'Device.ManagementServer.Password="{password}"')
            console.expect(" > ")
        console.sendline("Device.ManagementServer.EnableCWMP=0")
        console.expect(" > ")
        console.sendline("Device.ManagementServer.EnableCWMP=1")
        console.expect(" > ")
        console.sendline("exit")
        console.expect(r"/[a-zA-Z]* #")

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
            self._get_console("default_shell").execute_command(f"ifconfig {interface}"),
        ):
            return ifconfig_data[0]["mtu"]  # type: ignore[index]
        msg = f"ifconfig {interface} is not available"
        raise ValueError(msg)


class PrplDockerCPE(CPE, BoardfarmDevice):
    """PrplOS device class for a docker container."""

    def __init__(self, config: dict[str, Any], cmdline_args: Namespace) -> None:
        """Initialize PrplOS CPE container.

        :param config: configuration from inventory
        :type config: Dict
        :param cmdline_args: command line args
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)

        self._hw: PrplOSx86HW = PrplOSx86HW(config, cmdline_args)
        self._sw: PrplOSSW = None

    @property
    def config(self) -> dict:
        """Get device configuration.

        :returns: device configuration
        """
        return self._config

    @property
    def hw(self) -> PrplOSx86HW:
        """The PrplOS Hardware class object for x86 architecture.

        :return: object holding hardware component details.
        :rtype: PrplOSx86HW
        """
        return self._hw

    @property
    def sw(self) -> PrplOSSW:
        """The PrplOS Software class object.

        :return: object holding software component details.
        :rtype: PrplOSSW
        """
        return self._sw

    @hookimpl
    def boardfarm_device_boot(self, device_manager: DeviceManager) -> None:
        """Boardfarm hook implementation to boot the ETTH device.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        """
        self.hw.connect_to_consoles(self.device_name)
        self._sw = PrplOSSW(self._hw)
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
        self._sw = PrplOSSW(self._hw)
        self.hw.power_cycle()
        self.hw.wait_for_hw_boot()
        self.sw.wait_device_online()

        # This part is kept since the x86 version is missing
        # implementation to add ACS URL from DHCP vendor options
        if acs := device_manager.get_device_by_type(
            ACS,  # type: ignore[type-abstract]
        ):
            acs_url = acs.config.get(  # type: ignore[attr-defined]
                "acs_mib",
                "acs_server.boardfarm.com:7545",
            )
            self.sw.configure_management_server(url=acs_url)
        _LOGGER.info("TR069 CPE IP: %s", self.sw.cpe_id)

    def _is_http_gui_running(self) -> bool:
        return bool(
            self.hw.get_console("console").execute_command(
                f"netstat -nlp |grep {self.sw.lan_gateway_ipv4}:80",
            )
        )

    @hookimpl
    def boardfarm_device_configure(self) -> None:
        """Configure boardfarm device.

        :raises ConfigurationFailure: if the http service cannot be run
        """
        if retry(self._is_http_gui_running, 5):
            return
        self.hw.get_console("console").execute_command(
            "/etc/init.d/tr181-httpaccess stop",
        )
        sleep(5)
        self.hw.get_console("console").execute_command(
            "/etc/init.d/tr181-httpaccess start"
        )
        if retry(self._is_http_gui_running, 5):
            return
        msg = "Failed to start the GUI http daemon"
        raise ConfigurationFailure(msg)

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
        self._sw = PrplOSSW(self._hw)

    def get_interactive_consoles(self) -> dict[str, BoardfarmPexpect]:
        """Get interactive consoles of the device.

        :return: device interactive consoles
        :rtype: dict[str, BoardfarmPexpect]
        """
        return self.hw.get_interactive_consoles()
