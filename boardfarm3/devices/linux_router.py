"""Boardfarm Linux Router device module."""

from __future__ import annotations

import logging
from argparse import Namespace
from typing import TYPE_CHECKING

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import ConfigurationFailure
from boardfarm3.templates.core_router import CoreRouter

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect

_LOGGER = logging.getLogger(__name__)


class LinuxRouter(LinuxDevice, CoreRouter):
    """SSH-accessible Linux router container implementing CoreRouter.

    Connects via an authenticated SSH transport. During server_configure the
    frr service status is verified to confirm the routing daemon is active.
    """

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize LinuxRouter device.

        :param config: device configuration
        :type config: dict
        :param cmdline_args: command line arguments
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)

    @property
    def iface_dut(self) -> str:
        """Name of the router interface that faces the DUT.

        :return: interface name
        :rtype: str
        """
        return "cpe"

    @property
    def console(self) -> BoardfarmPexpect:
        """Return router console.

        :return: console
        :rtype: BoardfarmPexpect
        """
        return self._console

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Connect to the router container."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    def boardfarm_server_configure(self) -> None:
        """Verify that the frr routing service is active.

        :raises ConfigurationFailure: if the frr service is not running
        """
        _LOGGER.info(
            "Configuring %s(%s) device", self.device_name, self.device_type
        )
        output = self._console.execute_command("service frr status")
        if "running" not in output or "FAILED" in output:
            msg = (
                f"{self.device_name}: frr service is not running. "
                f"Output: {output!r}"
            )
            raise ConfigurationFailure(msg)
        _LOGGER.info("%s: frr service is active", self.device_name)

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Connect to the router without running the full boot sequence."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    async def boardfarm_skip_boot_async(self) -> None:
        """Async connect to the router without running the full boot sequence."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        await self._connect_async()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Disconnect from the router container."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    def add_route(
        self,
        destination: str,
        hop: str,
        gw_interface: str | None,
    ) -> None:
        """Add a route to a destination via a next-hop address.

        :param destination: destination network or IP address
        :type destination: str
        :param hop: IP address of the next hop
        :type hop: str
        :param gw_interface: exit interface name, or None to omit
        :type gw_interface: str | None
        """
        cmd = f"ip route add {destination} via {hop}"
        if gw_interface:
            cmd += f" dev {gw_interface}"
        self._console.execute_command(cmd)

    def delete_route(self, destination: str) -> None:
        """Delete a route to a destination.

        :param destination: destination network or IP address to remove
        :type destination: str
        """
        self._console.execute_command(f"ip route del {destination}")


if __name__ == "__main__":
    LinuxRouter(config={}, cmdline_args=Namespace())
