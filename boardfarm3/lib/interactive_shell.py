"""Boardfarm interactive shell module."""

import logging
import re
import sys
import time
from argparse import Namespace
from collections.abc import Callable
from typing import Any, Optional

import jedi
import pytest
from importlib_metadata import entry_points
from ptpython.ipython import IPythonInput, embed
from rich import print as rich_print
from rich.box import ASCII_DOUBLE_HEAD, Box
from rich.console import JustifyMethod
from rich.prompt import Prompt
from rich.table import Table

from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
from boardfarm3.lib.device_manager import DeviceManager
from boardfarm3.lib.utils import disable_logs


class OptionsTable:
    """Boardfarm interactive console options table."""

    def __init__(
        self, table_style: Box, title: Optional[str] = None, min_width: int = 80
    ) -> None:
        """Initialize the OptionsTable.

        :param table_style: table box style
        :type table_style: Box
        :param title: title of the table, defaults to None
        :type title: Optional[str], optional
        :param min_width: minimum with of the table, defaults to 100
        :type min_width: int, optional
        """
        self._table = Table(
            title=title, title_justify="center", box=table_style, min_width=min_width
        )
        self._actions: dict[str, tuple[Callable, tuple[Any, ...], dict[str, Any]]] = {}

    def add_column(
        self,
        name: str,
        justify: JustifyMethod = None,
        style: str = None,
        width: Optional[int] = None,
    ) -> None:
        """Add a table column.

        :param name: name of the column
        :type name: str
        :param justify: column content position, defaults to None
        :type justify: JustifyMethod, optional
        :param style: table content style, defaults to None
        :type style: str, optional
        :param width: column width, defaults to None
        :type width: Optional[int], optional
        """
        self._table.add_column(name, justify=justify, style=style, width=width)

    def add_option(
        self,
        option: str,
        description: str,
        function: Callable,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """Add an action item to the table.

        :param option: option name
        :type option: str
        :param description: option description
        :type description: str
        :param function: function to be called for this option
        :type function: Callable
        :param args: positional arguments to the function
        :type args: Tuple[Any, ...]
        :param kwargs: keyword arguments to the function
        :type kwargs: Dict[str, Any]
        """
        self._table.add_row(option, description)
        self._actions[option] = (function, args, kwargs)

    def show_table(self, exit_option: str, exit_option_description: str) -> None:
        """Show table and perform actions based on user input.

        :param exit_option: exit option name
        :type exit_option: str
        :param exit_option_description: exit option description
        :type exit_option_description: str
        """
        self._table.add_row(exit_option, exit_option_description)
        rich_print(self._table)
        while (
            option := Prompt.ask(
                "Enter your choice:", choices=list(self._actions.keys()) + [exit_option]
            )
        ) != exit_option:
            self._actions[option][0](
                *self._actions[option][1], **self._actions[option][2]
            )
            rich_print(self._table)

    def add_section(self) -> None:
        """Add a section in the table."""
        self._table.add_section()


def _start_interactive_session(
    device_name: str, console_name: str, console: BoardfarmPexpect
) -> None:
    rich_print(
        f"[magenta]Entering into {console_name} ({device_name})."
        " Press Ctrl + ] to exit."
    )
    console.start_interactive_session()
    print()  # fix for broken table after exiting the terminal


def _start_interactive_console(device: BoardfarmDevice) -> None:
    consoles = device.get_interactive_consoles()
    if not consoles:
        rich_print(
            f"[red]No console available for {device.device_name}. Please try"
            " another device.[/red]"
        )
        return
    if len(consoles) == 1:
        name, console_obj = consoles.popitem()
        _start_interactive_session(device.device_name, name, console_obj)
    elif len(consoles) > 1:
        table = OptionsTable(ASCII_DOUBLE_HEAD, min_width=60)
        table.add_column("Options", justify="center", style="cyan", width=1)
        table.add_column("Console Name", style="magenta")
        for index, console in enumerate(consoles.items(), start=1):
            table.add_option(
                str(index),
                console[0],
                _start_interactive_session,
                (
                    device.device_name,
                    console[0],
                    console[1],
                ),
                {},
            )
        table.add_section()
        table.show_table("q", "go back")


def _get_device_console_options(
    device_manager: DeviceManager,
) -> list[tuple[str, str, Callable[..., None], tuple[Any, ...], dict[str, Any]]]:
    console_options: list[
        tuple[str, str, Callable[..., None], tuple[Any, ...], dict[str, Any]]
    ] = []
    devices = device_manager.get_devices_by_type(BoardfarmDevice).values()
    max_length = max(len(f"{x.device_name} ({x.device_type})") for x in devices)
    for index, device in enumerate(
        sorted(devices, key=lambda item: item.device_name), start=1
    ):
        device_name = f"{device.device_name} ({device.device_type})"
        console_options.append(
            (
                str(index),
                (
                    f"{device_name: <{max_length}} -"
                    f" {len(device.get_interactive_consoles())} console(s)"
                ),
                _start_interactive_console,
                (device,),
                {},
            )
        )
    return console_options


def _configure_repl(repl: IPythonInput) -> None:
    """Configure a few useful defaults."""
    repl.show_signature = True
    repl.show_docstring = True
    repl.show_line_numbers = True
    repl.highlight_matching_parenthesis = True


def _interactive_ptpython_shell(
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
        rich_print(
            f"[green]Use devices.<name> to access one of {list(vars(devices).keys())}"
        )
    embed(configure=_configure_repl)


def _run_boardfarm_tests() -> None:
    pytest_arguments = [
        "--self-contained-html",
        f"--html=report-{int(time.time())}.html",
    ]
    tests = Prompt.ask(
        "[magenta]Enter comma separated test paths or JIRA IDs",
    )
    jira_test_ids: list[str] = []
    for test in tests.split(","):
        if re.match(r"^MVX_TST-\d+$", test.strip()):
            jira_test_ids.append(f"test_{test}.py")
            continue
        pytest_arguments.append(test)
    pytest_arguments.extend(["-k", f"{' or '.join(jira_test_ids)}"])
    pexpect_logger = logging.getLogger("pexpect")
    with disable_logs(), disable_logs("pexpect"):
        pexpect_logger.propagate = True
        pytest.main(sys.argv[1:] + pytest_arguments)
        pexpect_logger.propagate = False


def get_interactive_console_options(
    device_manager: DeviceManager, cmdline_args: Namespace
) -> OptionsTable:
    """Return options table with all boardfarm interactive shell options.

    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :return: option table with boardfarm interactive shell options
    :rtype: OptionsTable
    """
    table = OptionsTable(ASCII_DOUBLE_HEAD, "BOARDFARM INTERACTIVE SHELL")
    table.add_column("Options", justify="center", style="cyan")
    table.add_column("Description", style="magenta")
    for option in _get_device_console_options(device_manager):
        table.add_option(*option)
    table.add_section()
    table.add_option(
        "p",
        "python interactive shell(ptpython)",
        _interactive_ptpython_shell,
        (cmdline_args, device_manager),
        {},
    )
    if entry_points(group="pytest11", name="pytest_boardfarm"):
        table.add_option(
            "e", "execute boardfarm automated test(s)", _run_boardfarm_tests, (), {}
        )
    return table
