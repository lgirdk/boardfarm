"""Banana Pi runnign RDKB.

Almost identical to the RPiRdkB class (note the "almost").
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.devices.rpirdkb_cpe import RPiRDKBCPE, RPiRDKBHW, RPiRDKBSW
from boardfarm3.lib.device_manager import get_device_manager
from boardfarm3.templates.acs import ACS

if TYPE_CHECKING:
    from argparse import Namespace

    from boardfarm3.lib.device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)


class BananaPiRDKBHW(RPiRDKBHW):
    """The 🍌π Hw class."""

    @property
    def _shell_prompt(self) -> list[str]:
        """Console prompt.

        :return: the shell prompt
        :rtype: list[str]
        """
        return [r"(ser2net)|(root@Filogic-GW:.*#)"]

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
    """The 🍌π Sw class."""

    _hw: BananaPiRDKBHW

    def __init__(self, hardware: BananaPiRDKBHW) -> None:
        """Initialise the 🍌π sofware class.

        :param hardware: the board hw object
        :type hardware: BananaPiRDKBHW
        """
        super().__init__(hardware)

    @property
    def tr69_cpe_id(self) -> str:
        """Same all same all.

        :return: cpe id
        :rtype: str
        """
        return self._hw.config["serial"]


class BananaPiRDKBCPE(RPiRDKBCPE, BoardfarmDevice):
    """The 🍌π CPE class."""

    def __init__(self, config: dict[str, Any], cmdline_args: Namespace) -> None:
        """Initialize 🍌π CPE container.

        :param config: configuration from inventory
        :type config: Dict
        :param cmdline_args: command line args
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)
        self._hw: BananaPiRDKBHW = BananaPiRDKBHW(config, cmdline_args)

    @property
    def hw(self) -> BananaPiRDKBHW:
        """The BananaPi Hardware class object.

        :return: object holding hardware component details.
        :rtype: RPiRDKBHW
        """
        return self._hw

    @property
    def sw(self) -> BananaPiRDKBSW:
        """The BananaPi Software class object.

        :return: object holding software component details.
        :rtype: RPiRDKBSW
        """
        return self._sw

    def _prep_device(self, device_manager: DeviceManager) -> None:
        acs = next(iter(device_manager.get_devices_by_type(ACS).values()))
        self._hw._console.execute_command("ip route add default via 10.1.1.1")
        self._sw.dmcli.SPV(
            param="Device.ManagementServer.EnableCWMP", value="false", type_set="bool"
        )
        self._sw.dmcli.SPV(
            param="Device.ManagementServer.URL",
            value=acs.config["acs_mib"],
        )
        self._sw.dmcli.SPV(
            param="Device.ManagementServer.PeriodicInformInterval",
            value="10",
            type_set="uint",
        )
        self._sw.dmcli.SPV(
            param="Device.ManagementServer.EnableCWMP", value="true", type_set="bool"
        )

    @hookimpl
    def boardfarm_device_boot(self, device_manager: DeviceManager) -> None:
        """Boardfarm hook implementation to boot the ETTH device.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        """
        raise NotImplementedError

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
        """Boardfarm hook implementation to shutdown the ETTH device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self.hw.disconnect_from_consoles()
