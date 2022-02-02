"""Boardfarm base device template."""

from argparse import Namespace
from typing import Dict

from boardfarm.lib.boardfarm_pexpect import BoardfarmPexpect


class BoardfarmDevice:
    """Boardfarm base device which all devices inherit from."""

    def __init__(self, config: Dict, cmdline_args: Namespace) -> None:
        """Initialize boardfarm base device.

        :param config: divice configuration
        :param cmdline_args: command line arguments
        """
        self._config: Dict = config
        self._cmdline_args = cmdline_args

    @property
    def config(self) -> Dict:
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

    # pylint: disable=no-self-use  # to avoid mypy signature mismatch error
    def get_interactive_consoles(self) -> Dict[str, BoardfarmPexpect]:
        """Get interactive consoles from device.

        :returns: interactive consoles of the device
        """
        return {}
