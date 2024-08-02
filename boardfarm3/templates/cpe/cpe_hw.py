"""CPE HW Template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from boardfarm3.templates.core_router import CoreRouter

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.templates.tftp import TFTP

# Type hinting
TerminationSystem = CoreRouter


class CPEHW(ABC):
    """CPE hardware template."""

    @property
    @abstractmethod
    def config(self) -> dict[str, Any]:
        """Device config."""
        raise NotImplementedError

    @property
    @abstractmethod
    def mac_address(self) -> str:
        """Get the MAC address."""
        raise NotImplementedError

    @property
    @abstractmethod
    def wan_iface(self) -> str:
        """WAN interface name."""
        raise NotImplementedError

    @property
    @abstractmethod
    def mta_iface(self) -> str:
        """MTA interface name."""
        raise NotImplementedError

    @abstractmethod
    def connect_to_consoles(self, device_name: str) -> None:
        """Connect to the consoles.

        :param device_name: name of the device
        :type device_name: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_console(self, console_name: str) -> BoardfarmPexpect:
        """Return console instance with the given name.

        :param console_name: name of the console
        :type console_name: str
        :raises ValueError: on unknown console name
        :return: console instance with given name
        :rtype: BoardfarmPexpect
        """
        raise NotImplementedError

    @abstractmethod
    def power_cycle(self) -> None:
        """Power cycle the board via HW (usually via a PDU device)."""
        raise NotImplementedError

    @abstractmethod
    def wait_for_hw_boot(self) -> None:
        """Wait for the HW boot messages(bootloader)."""
        raise NotImplementedError

    @abstractmethod
    def flash_via_bootloader(
        self,
        image: str,
        tftp_devices: dict[str, TFTP],
        termination_sys: TerminationSystem = None,
        method: str | None = None,
    ) -> None:
        """Flash cable modem via the bootloader.

        :param image: image name
        :type image: str
        :param tftp_devices: a list of LAN side TFTP devices
        :type tftp_devices: dict[str, TFTP]
        :param termination_sys: the termination system device (e.g. CMTS),
            defaults to None
        :type termination_sys: TerminationSystem
        :param method: flash method, defaults to None
        :type method: str, optional
        :raises NotImplementedError: as a safety measure
        """
        raise NotImplementedError

    @abstractmethod
    def disconnect_from_consoles(self) -> None:
        """Disconnect/Close the console connections."""
        raise NotImplementedError

    @abstractmethod
    def get_interactive_consoles(self) -> dict[str, BoardfarmPexpect]:
        """Get interactive consoles of the device.

        :returns: device interactive consoles
        :rtype: Dict[str, BoardfarmPexpect]
        """
        raise NotImplementedError
