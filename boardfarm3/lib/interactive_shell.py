"""Boardfarm interactive shell module."""

from __future__ import annotations

import logging
import re
import sys
import time
from argparse import Namespace
from typing import TYPE_CHECKING, Any

import jedi
import pytest
from importlib_metadata import entry_points
from ptpython.ipython import IPythonInput, embed
from rich import print as rich_print
from rich.box import HORIZONTALS
from rich.prompt import Prompt
from rich.table import Table

from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.lib.utils import disable_logs

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import JustifyMethod

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.device_manager import DeviceManager


class OptionsTable:
    """Boardfarm interactive console options table."""

    def __init__(self, title: str | None = None) -> None:
        """Initialize the OptionsTable.

        :param title: title of the table, defaults to None
        :type title: Optional[str], optional
        """
        self._table = Table(
            title=title,
            title_justify="center",
            box=HORIZONTALS,
            show_lines=True,
        )
        self._actions: dict[str, tuple[Callable, tuple[Any, ...], dict[str, Any]]] = {}

    def add_column(
        self,
        name: str,
        justify: JustifyMethod | None = None,
        style: str | None = None,
        width: int | None = None,
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
        column_data: tuple[str, ...],
        function: Callable,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """Add an action item to the table.

        :param column_data: table column data
        :type column_data: tuple[str, ...]
        :param function: function to be called for this option
        :type function: Callable
        :param args: positional arguments to the function
        :type args: Tuple[Any, ...]
        :param kwargs: keyword arguments to the function
        :type kwargs: Dict[str, Any]
        """
        self._table.add_row(*column_data)
        self._actions[column_data[0]] = (function, args, kwargs)

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
                "Enter your choice:",
                choices=[*list(self._actions.keys()), exit_option],
            )
        ) != exit_option:
            self._actions[option][0](
                *self._actions[option][1],
                **self._actions[option][2],
            )
            rich_print(self._table)


def _start_interactive_session(
    device_name: str,
    console_name: str,
    console: BoardfarmPexpect,
) -> None:
    rich_print(
        f"[magenta]Entering into {console_name} ({device_name})."
        " Press Ctrl + ] to exit.",
    )
    console.start_interactive_session()
    print()  # fix for broken table after exiting the terminal  # noqa: T201


def _start_interactive_console(device: BoardfarmDevice) -> None:
    consoles = device.get_interactive_consoles()
    if not consoles:
        rich_print(
            f"[red]No console available for {device.device_name}. Please try"
            " another device.[/red]",
        )
        return
    if len(consoles) == 1:
        name, console_obj = consoles.popitem()
        _start_interactive_session(device.device_name, name, console_obj)
    elif len(consoles) > 1:
        table = OptionsTable()
        table.add_column("Choice", justify="center", style="cyan")
        table.add_column("Console Name", style="magenta")
        for index, console in enumerate(consoles.items(), start=1):
            table.add_option(
                (str(index), console[0]),
                _start_interactive_session,
                (
                    device.device_name,
                    console[0],
                    console[1],
                ),
                {},
            )
        table.show_table("q", "go back")


def _get_device_console_options(
    device_manager: DeviceManager,
) -> list[tuple[tuple[str, ...], Callable[..., None], tuple[Any, ...], dict[str, Any]]]:
    console_options: list[
        tuple[
            tuple[str, ...],
            Callable[..., None],
            tuple[Any, ...],
            dict[str, Any],
        ]
    ] = []
    devices = device_manager.get_devices_by_type(BoardfarmDevice).values()
    for index, device in enumerate(
        sorted(devices, key=lambda item: item.device_name),
        start=1,
    ):
        console_options.append(
            (
                (
                    str(index),
                    f"{device.device_name} ({device.device_type})",
                    str(len(device.get_interactive_consoles())),
                ),
                _start_interactive_console,
                (device,),
                {},
            ),
        )
    return console_options


def _configure_repl(repl: IPythonInput) -> None:
    """Configure a few useful defaults.

    :param repl: python input
    """
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
    __int._allow_descriptor_getattr_default = False  # type: ignore[attr-defined]  # noqa: SLF001  # pylint: disable=line-too-long

    if cmdline_args.legacy:
        devices = Namespace(**device_manager.get_devices_by_type(BoardfarmDevice))
        rich_print(
            f"[green]Use devices.<name> to access one of {list(vars(devices).keys())}",
        )
    embed(configure=_configure_repl)


def _run_boardfarm_tests() -> None:
    pytest_arguments: list[str] = [
        "--self-contained-html",
        f"--html=report-{int(time.time())}.html",
    ]
    tests: str = Prompt.ask(
        "[magenta]Enter comma separated test paths or JIRA IDs",
    )
    jira_test_ids: list[str] = []
    for test in tests.split(","):
        if re.match(r"^MVX_TST-\d+$", test.strip()) is not None:
            jira_test_ids.append(f"test_{test}.py")
        else:
            pytest_arguments.append(test)
    pytest_arguments.extend(["-k", f"{' or '.join(jira_test_ids)}"])
    pexpect_logger = logging.getLogger("pexpect")
    with disable_logs(), disable_logs("pexpect"):
        pexpect_logger.propagate = True
        pytest.main(sys.argv[1:] + pytest_arguments)
        pexpect_logger.propagate = False


def _add_session_marker_in_console_logs() -> None:
    message = Prompt.ask(
        "[magenta]Enter your message",
        default="---",
        show_default=False,
    )
    for (
        name,
        logger,
    ) in logging.root.manager.loggerDict.items():  # pylint: disable=no-member
        if isinstance(logger, logging.Logger) and "pexpect." in name:
            logger.debug("#" * 80)
            logger.debug("{log_msg}", extra={"log_msg": f"#{message.upper(): ^78}#"})
            logger.debug("#" * 80)


def get_interactive_console_options(
    device_manager: DeviceManager,
    cmdline_args: Namespace,
) -> OptionsTable:
    """Return options table with all boardfarm interactive shell options.

    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    :param cmdline_args: command line arguments
    :type cmdline_args: Namespace
    :return: option table with boardfarm interactive shell options
    :rtype: OptionsTable
    """
    table = OptionsTable("BOARDFARM INTERACTIVE SHELL")
    table.add_column("Choice", justify="center", style="cyan")
    table.add_column("Description", style="magenta")
    table.add_column("Consoles", justify="center")
    for option in _get_device_console_options(device_manager):
        table.add_option(*option)
    table.add_option(
        ("p", "python interactive shell (ptpython)"),
        _interactive_ptpython_shell,
        (cmdline_args, device_manager),
        {},
    )
    if entry_points(group="pytest11", name="pytest_boardfarm"):
        table.add_option(
            ("e", "execute boardfarm automated test(s)"),
            _run_boardfarm_tests,
            (),
            {},
        )
    if cmdline_args.save_console_logs:
        table.add_option(
            ("m", "add custom marker in console logs"),
            _add_session_marker_in_console_logs,
            (),
            {},
        )
    return table
