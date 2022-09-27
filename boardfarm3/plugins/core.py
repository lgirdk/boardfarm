"""Boardfarm core plugin."""

import logging
from argparse import ArgumentParser, Namespace

import jedi
from pluggy import PluginManager
from ptpython.ipython import IPythonInput, embed
from termcolor import colored

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
from boardfarm3.lib.device_manager import DeviceManager
from boardfarm3.plugins.hookspecs import devices as Devices


@hookimpl
def boardfarm_add_hookspecs(plugin_manager: PluginManager) -> None:
    """Add boardfarm core plugin hookspecs.

    :param plugin_manager: plugin manager
    """
    plugin_manager.add_hookspecs(Devices)


@hookimpl
def boardfarm_add_cmdline_args(argparser: ArgumentParser) -> None:
    """Add boardfarm command line arguments.

    :param argparser: argument parser
    """
    argparser.add_argument("--board-name", required=True, help="Board name")
    argparser.add_argument(
        "--env-config", required=True, help="Environment JSON config file path"
    )
    argparser.add_argument(
        "--inventory-config", required=True, help="Inventory JSON config file path"
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


@hookimpl
def boardfarm_cmdline_parse(
    argparser: ArgumentParser, cmdline_args: list[str]
) -> Namespace:
    """Parse command line arguments.

    :param argparser: argument parser instance
    :param cmdline_args: command line arguments list
    :returns: command line arguments
    """
    return argparser.parse_args(args=cmdline_args)


def _get_device_name_from_user(
    devices_dict: dict[str, BoardfarmDevice], exit_code: str
) -> str:
    """Get device name from user."""
    print("----------------------------------------------")
    print("ID  Device name      Device type      Consoles")
    print("----------------------------------------------")
    device_names = sorted(devices_dict.keys())
    for i, device_name in enumerate(device_names, start=1):
        device = devices_dict.get(device_name)
        num_consoles = len(device.get_interactive_consoles())
        print(f"{i: >2}  {device_name: <16} {device.device_type: <16} {num_consoles}")
    print("----------------------------------------------")
    print(f"{'p': >2} {' python': <16} {' interactive shell': <16}")

    print(f"\nEnter '{exit_code}' to exit the interactive shell.\n")
    device_name = None
    device_id = input("Please enter a device ID: ")
    if device_id == exit_code:
        device_name = device_id
    elif device_id == "p":
        device_name = "python"
    elif not device_id.isdigit():
        print("\nERROR: Wrong input. Please try again.\n")
    elif int(device_id) > len(device_names):
        print("\nERROR: Wrong device ID. Please try again.\n")
    else:
        device_name = device_names[int(device_id) - 1]
    return device_name


def _get_console_name_from_user(
    device_name: str, consoles: dict[str, BoardfarmPexpect]
) -> str:
    """Get device console name from user."""
    console_name = None
    console_names = sorted(consoles.keys())
    while True:
        if not console_names:
            print(
                f"\nERROR: No console available for {device_name}. "
                "Please try another device.\n"
            )
            break
        if len(console_names) == 1:
            console_name = console_names[0]
            break
        print(f"{device_name}' has more than one console.")
        console_ids = " ".join(
            [f"{x}) {y:16}" for x, y in enumerate(console_names, start=1)]
        )
        print(f"\n{console_ids} q) go back.\n")
        console_id = input("Please enter a console ID: ")
        if not console_id.isdigit():
            print("\nERROR: Wrong input. Please try again.\n")
            continue
        if int(console_id) > len(console_names):
            print("\nERROR: Wrong console ID. Please try again.\n")
            continue
        console_name = console_names[int(console_id) - 1]
        break
    return console_name


def _configure_repl(repl: IPythonInput) -> None:
    """Configure a few useful defaults."""
    repl.show_signature = True
    repl.show_docstring = True
    repl.show_line_numbers = True
    repl.highlight_matching_parenthesis = True


def _interactive_ptpython_shell(
    config: BoardfarmConfig,  # pylint: disable=unused-argument
    cmdline_args: Namespace,
    device_manager: DeviceManager,
) -> None:

    logging.getLogger("parso").setLevel("INFO")
    logging.getLogger("asyncio").setLevel("INFO")

    # The following prevents __getattr__ from
    # running the object prperties (which happens
    # on autocompletion)
    __int = jedi.Interpreter

    # pylint: disable=protected-access
    __int._allow_descriptor_getattr_default = False  # type: ignore[attr-defined]

    if cmdline_args.legacy:
        devices = Namespace(**device_manager.get_devices_by_type(BoardfarmDevice))
        print(
            colored(
                f"Use devices.<name> to access one of {list(vars(devices).keys())}",
                color="green",
                attrs=["bold"],
            )
        )
    embed(configure=_configure_repl)


@hookimpl(trylast=True)
def boardfarm_post_deploy_devices(
    config: BoardfarmConfig, cmdline_args: Namespace, device_manager: DeviceManager
) -> None:
    """Enter into boardfarm interactive session after deployment.

    :param device_manager: device manager
    """
    print("----------------------------------------------\n")
    print("         BOARDFARM INTERACTIVE SHELL\n")
    exit_code = "q"
    while True:
        devices_dict = device_manager.get_devices_by_type(BoardfarmDevice)
        if not devices_dict:
            print("No device available in the environment.")
            break
        try:
            device_name = _get_device_name_from_user(devices_dict, exit_code)
        except (KeyboardInterrupt, EOFError) as err:
            print(colored(f"\nReceived {repr(err)}", color="red"))
            continue
        if device_name == exit_code:
            break
        if device_name is None:
            continue
        if device_name == "python":
            _interactive_ptpython_shell(config, cmdline_args, device_manager)
            continue
        device = devices_dict.get(device_name)
        consoles = device.get_interactive_consoles()
        console_name = _get_console_name_from_user(device_name, consoles)
        if console_name is None:
            continue
        print(f"\nEntering into {console_name}({device_name})\n")
        selected_console = consoles.get(console_name)
        selected_console.start_interactive_session()
        print("\n")
    print("Bye.")
