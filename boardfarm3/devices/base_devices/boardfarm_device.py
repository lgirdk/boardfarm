"""Boardfarm base device template."""

from argparse import Namespace

from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class BoardfarmDevice:
    """Boardfarm base device which all devices inherit from."""

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize boardfarm base device.

        :param config: device configuration
        :param cmdline_args: command line arguments
        """
        self._config: dict = config
        self._cmdline_args = cmdline_args

    @property
    def config(self) -> dict:
        """Get device configuration.

        :returns: device configuration
        """
        return self._config

    @property
    def device_name(self) -> str:
        """Get name of the device.

        :returns: device name
        """
        return self._config.get("name")

    @property
    def device_type(self) -> str:
        """Get type of the device.

        :returns: device type
        """
        return self._config.get("type")

    def get_interactive_consoles(self) -> dict[str, BoardfarmPexpect]:
        """Get interactive consoles from device.

        :returns: interactive consoles of the device
        """
        return {}
