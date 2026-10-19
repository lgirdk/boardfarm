"""Non-interactive session modes: the extension point.

A session runs in ``interact`` mode unless its config names another mode. A
plugin provides a mode by returning ``{name: SessionMode subclass}`` from the
``boardfarm_add_api_modes`` hook. In such a mode the agent never builds
devices: the mode owns the board for the length of its run.
"""

from __future__ import annotations

import argparse
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import pluggy

from boardfarm3.api import hookspecs as api_hookspecs
from boardfarm3.api.entrypoints import disabled_plugins, load_entrypoints

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

INTERACT = "interact"

_ENTRYPOINT_GROUP = "boardfarm_api"
_HOOK_NAME = "boardfarm_add_api_modes"
_log = logging.getLogger(__name__)


class ModeRequestError(ValueError):
    """The session's ``run`` request cannot be carried out by its mode."""


@dataclass(frozen=True)
class Command:
    """One process a mode runs.

    :param argv: program and arguments
    :type argv: list[str]
    :param env: the complete environment for the process
    :type env: dict[str, str]
    :param cwd: working directory
    :type cwd: Path
    :param display: argv as reported in status, credentials shown as ``***``
    :type display: list[str]
    """

    argv: list[str]
    env: dict[str, str]
    cwd: Path
    display: list[str]


@dataclass(frozen=True)
class ModeContext:  # pylint: disable=too-many-instance-attributes
    """What a mode gets from the session that runs it.

    :param session_id: the session's id
    :type session_id: str
    :param board_name: the board the session leased
    :type board_name: str
    :param payload: the session payload (inventory and env)
    :type payload: dict[str, Any]
    :param options: the session's boardfarm options, as sent in the config call
    :type options: dict[str, Any]
    :param run: the mode-specific request
    :type run: dict[str, Any]
    :param run_dir: where the run's reports and logs go; part of every bundle
    :type run_dir: Path
    :param private_dir: a 0700 directory removed when the run ends; never archived
    :type private_dir: Path
    :param boardfarm_parser: every boardfarm command-line flag the plugins register
    :type boardfarm_parser: argparse.ArgumentParser
    :param emit: appends one line to the session's console stream
    :type emit: Callable[[str], None]
    :param finished: tells the session the run has ended
    :type finished: Callable[[], None]
    """

    session_id: str
    board_name: str
    payload: dict[str, Any]
    options: dict[str, Any]
    run: dict[str, Any]
    run_dir: Path
    private_dir: Path
    boardfarm_parser: argparse.ArgumentParser
    emit: Callable[[str], None]
    finished: Callable[[], None]


class SessionMode(ABC):
    """A way to use a session's board other than interacting with it."""

    #: name of the console stream the mode's output goes to
    stream_name: ClassVar[str] = "run"

    def __init__(self, context: ModeContext) -> None:
        """Keep the context.

        :param context: what the session hands the mode
        :type context: ModeContext
        """
        self.context = context

    @abstractmethod
    def validate(self) -> None:
        """Check ``context.run`` and ``context.options`` before anything starts.

        :raises ModeRequestError: when the request cannot be carried out
        """

    @abstractmethod
    async def start(self) -> None:
        """Start the run and return once it is under way."""

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Return the run summary reported by ``/run`` and ``/session``.

        :return: the run summary
        :rtype: dict[str, Any]
        """

    @abstractmethod
    def running_since(self) -> float | None:
        """Return when the run started, while it is still running.

        :return: start time, or None once it has ended
        :rtype: float | None
        """

    @abstractmethod
    async def cancel(self) -> bool:
        """Stop the run.

        :return: False when nothing was running
        :rtype: bool
        """

    @abstractmethod
    async def wait(self) -> None:
        """Return once the run has ended."""


def boardfarm_argparser(
    plugin_manager: pluggy.PluginManager | None,
) -> argparse.ArgumentParser:
    """Return a parser holding every boardfarm flag the plugins register.

    :param plugin_manager: the session's boardfarm plugin manager, if it has one
    :type plugin_manager: pluggy.PluginManager | None
    :return: the parser; empty without a plugin manager
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(add_help=False)
    if plugin_manager is not None:
        plugin_manager.hook.boardfarm_add_cmdline_args(argparser=parser)
    return parser


def iter_plugin_modes(
    plugin_manager: pluggy.PluginManager,
) -> Iterator[tuple[str, type[SessionMode]]]:
    """Yield every mode the plugins offer, calling one plugin at a time.

    Mirrors ``iter_plugin_bundles``: a plugin that raises costs only its own
    modes, and disabled plugins are skipped. It is a separate loop because
    that function's log records belong to ``boardfarm3.api.routers``.

    :param plugin_manager: manager with ``boardfarm_api`` plugins registered
    :type plugin_manager: pluggy.PluginManager
    :yield: ``(name, mode class)`` pairs
    :rtype: Iterator[tuple[str, type[SessionMode]]]
    """
    registered = list(plugin_manager.list_name_plugin())
    disabled = disabled_plugins()
    for plugin_name, plugin in registered:
        if plugin_name in disabled:
            continue
        caller = plugin_manager.subset_hook_caller(
            _HOOK_NAME,
            remove_plugins=[other for _, other in registered if other is not plugin],
        )
        try:
            contributions: list[dict[str, type[SessionMode]]] = caller()
            offered = [item for modes in contributions for item in modes.items()]
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            _log.exception(
                "boardfarm_api plugin %r raised while contributing modes; skipped",
                plugin_name,
            )
            continue
        yield from offered


def collect_modes(
    plugin_manager: pluggy.PluginManager,
) -> dict[str, type[SessionMode]]:
    """Return the modes the plugins offer, without ``interact`` or duplicates.

    :param plugin_manager: manager with ``boardfarm_api`` plugins registered
    :type plugin_manager: pluggy.PluginManager
    :return: mode classes by name
    :rtype: dict[str, type[SessionMode]]
    """
    modes: dict[str, type[SessionMode]] = {}
    for name, mode_class in iter_plugin_modes(plugin_manager):
        if name == INTERACT or name in modes:
            _log.warning("session mode %r is reserved or offered twice; ignored", name)
            continue
        modes[name] = mode_class
    return modes


def load_plugin_modes() -> dict[str, type[SessionMode]]:
    """Discover the modes contributed through ``boardfarm_api`` entry points.

    :return: mode classes by name; ``interact`` never appears
    :rtype: dict[str, type[SessionMode]]
    """
    try:
        plugin_manager = pluggy.PluginManager(_ENTRYPOINT_GROUP)
        plugin_manager.add_hookspecs(api_hookspecs)
        load_entrypoints(plugin_manager, _ENTRYPOINT_GROUP, skip=disabled_plugins())
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        _log.exception("failed to load %s entrypoints", _ENTRYPOINT_GROUP)
        return {}
    return collect_modes(plugin_manager)
