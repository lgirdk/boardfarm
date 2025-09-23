"""Boardfarm plugin to support parsing the config files passed as arguments."""

from argparse import Namespace
from typing import Any

from boardfarm3 import hookimpl
from boardfarm3.lib.boardfarm_config import get_inventory_config


@hookimpl
def boardfarm_reserve_devices(cmdline_args: Namespace) -> dict[str, Any]:
    """Return inventory config after reservation check.

    In scenarios where board reservation is not needed,
    the devices can be accessed directly by using no_reservation plugin.

    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :return: inventory configuration
    :rtype: dict[str, Any]
    """
    return get_inventory_config(cmdline_args.board_name, cmdline_args.inventory_config)
