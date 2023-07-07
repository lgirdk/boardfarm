"""Boardfarm core plugin."""
from argparse import ArgumentParser, ArgumentTypeError, Namespace

from pluggy import PluginManager

from boardfarm3 import hookimpl
from boardfarm3.lib.device_manager import DeviceManager
from boardfarm3.lib.interactive_shell import get_interactive_console_options
from boardfarm3.plugins.hookspecs import devices as Devices


def _non_empty_str(arg: str) -> str:
    """Type to check boardfarm/pytest command line arguments empty value.

    :param arg: command line argument
    :type arg: str
    :raises ArgumentTypeError: raises argparse ArgumentTypeError
                    for empty argument values
    :return: arg if the argument is non empty
    :rtype: str
    """
    if arg:
        return arg
    message = "Argument value should not be empty"
    raise ArgumentTypeError(message)


@hookimpl
def boardfarm_add_hookspecs(plugin_manager: PluginManager) -> None:
    """Add boardfarm core plugin hookspecs.

    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    """
    plugin_manager.add_hookspecs(Devices)


@hookimpl
def boardfarm_add_cmdline_args(argparser: ArgumentParser) -> None:
    """Add boardfarm command line arguments.

    :param argparser: argument parser
    :type argparser: ArgumentParser
    """
    argparser.add_argument(
        "--board-name",
        type=_non_empty_str,
        required=True,
        help="Board name",
    )
    argparser.add_argument(
        "--env-config",
        type=_non_empty_str,
        required=True,
        help="Environment JSON config file path",
    )
    argparser.add_argument(
        "--inventory-config",
        type=_non_empty_str,
        required=True,
        help="Inventory JSON config file path",
    )
    argparser.add_argument(
        "--legacy",
        action="store_true",
        help="allows for devices.<device> obj to be exposed (only for legacy use)",
    )
    argparser.add_argument(
        "--skip-boot",
        action="store_true",
        help="Skips the booting process, all devices will be used as they are",
    )
    argparser.add_argument(
        "--skip-contingency-checks",
        action="store_true",
        help="Skip contingency checks while running tests",
    )
    argparser.add_argument(
        "--save-console-logs",
        action="store_true",
        help="Save console logs to the disk",
    )


@hookimpl
def boardfarm_cmdline_parse(
    argparser: ArgumentParser,
    cmdline_args: list[str],
) -> Namespace:
    """Parse command line arguments.

    :param argparser: argument parser instance
    :type argparser: ArgumentParser
    :param cmdline_args: command line arguments list
    :type cmdline_args: list[str]
    :return: command line arguments
    :rtype: Namespace
    """
    return argparser.parse_args(args=cmdline_args)


@hookimpl(trylast=True)
def boardfarm_post_deploy_devices(
    cmdline_args: Namespace,
    device_manager: DeviceManager,
) -> None:
    """Enter into boardfarm interactive session after deployment.

    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    get_interactive_console_options(device_manager, cmdline_args).show_table(
        "q",
        "exit",
    )
