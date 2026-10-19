"""Non-interactive session modes: the extension point.

A session runs in ``interact`` mode unless its config names another mode. A
plugin provides a mode by returning ``{name: SessionMode subclass}`` from the
``boardfarm_add_api_modes`` hook. In such a mode the agent never builds
devices: the mode owns the board for the length of its run.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import signal
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar

import pluggy

from boardfarm3.api import hookspecs as api_hookspecs
from boardfarm3.api.entrypoints import disabled_plugins, load_entrypoints

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

INTERACT = "interact"
CANCEL_GRACE_ENV = "BOARDFARM_RUN_CANCEL_GRACE"

_DEFAULT_CANCEL_GRACE = 60.0
_TERM_GRACE = 5.0
_DRAIN_TIMEOUT = 2.0
_READ_CHUNK = 64 * 1024
_MAX_LINE = 64 * 1024
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


class SubprocessRun(SessionMode):  # pylint: disable=too-many-instance-attributes
    """A mode whose run is one subprocess supervised by the agent.

    The process gets its own process group, so a cancel reaches what it
    started (browsers, helpers). Every output line goes to the console stream
    and to ``<run_dir>/<stream_name>.log``. The final status is written to
    ``<run_dir>/run.json``.
    """

    def __init__(self, context: ModeContext) -> None:
        """Prepare an unstarted run.

        :param context: what the session hands the mode
        :type context: ModeContext
        """
        super().__init__(context)
        self._command: Command | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._log_file: BinaryIO | None = None
        self._pump_task: asyncio.Task[None] | None = None
        self._cancel_task: asyncio.Task[None] | None = None
        self._done = asyncio.Event()
        self._started_at: float | None = None
        self._ended_at: float | None = None
        self._exit_code: int | None = None
        self._cancelled = False

    @abstractmethod
    def command(self) -> Command:
        """Return the process to run.

        :return: argv, environment, working directory and display form
        :rtype: Command
        """

    @abstractmethod
    def summary(self, exit_code: int | None, *, cancelled: bool) -> dict[str, Any]:
        """Return the mode's own status fields.

        :param exit_code: the exit code, or None while the run is going
        :type exit_code: int | None
        :param cancelled: whether a cancel was requested
        :type cancelled: bool
        :return: fields merged into ``status()``
        :rtype: dict[str, Any]
        """

    async def start(self) -> None:
        """Spawn the process and start streaming its output.

        :raises BaseException: whatever stopped the process from starting
            (usually OSError); the pipe and the log are released before it
            propagates
        """
        command = self.command()
        self._log_file = self._open_log()
        # The process writes to a pipe this class owns. asyncio's own stdout
        # pipe would tie Process.wait() to its closing, and a descendant
        # holding it would then block the exit.
        read_fd, write_fd = os.pipe()
        try:
            self._process = await asyncio.create_subprocess_exec(
                *command.argv,
                cwd=command.cwd,
                env=command.env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=write_fd,
                stderr=write_fd,
                start_new_session=True,
            )
        except BaseException:
            os.close(read_fd)
            self._log_file.close()
            self._log_file = None
            raise
        finally:
            os.close(write_fd)
        self._command = command
        self._started_at = time.time()
        self._pump_task = asyncio.create_task(self._pump(read_fd))

    def _open_log(self) -> BinaryIO:
        self.context.run_dir.mkdir(parents=True, exist_ok=True)
        return (self.context.run_dir / f"{self.stream_name}.log").open("ab")

    async def _pump(self, read_fd: int) -> None:
        process = self._process
        log_file = self._log_file
        if process is None or log_file is None:
            return
        output = asyncio.StreamReader()
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(output), os.fdopen(read_fd, "rb", 0)
        )
        reader = asyncio.create_task(self._read_output(output, log_file))
        try:
            self._exit_code = await process.wait()
            # A descendant in its own session can hold the pipe open after the
            # process exits; drain briefly, then stop listening.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(reader, _DRAIN_TIMEOUT)
        finally:
            reader.cancel()
            transport.close()
            with contextlib.suppress(OSError):
                log_file.close()
            self._ended_at = time.time()
            self._done.set()
            self._write_final_status()
            self.context.finished()

    async def _read_output(
        self, stdout: asyncio.StreamReader, log_file: BinaryIO
    ) -> None:
        pending = b""
        tee = True
        try:
            while chunk := await stdout.read(_READ_CHUNK):
                # A failed log stops being written; the pipe is drained regardless.
                if tee:
                    tee = self._tee(log_file, chunk)
                pending = self._emit_lines(pending + chunk)
        finally:
            if pending:
                self._emit_text(pending)

    def _tee(self, log_file: BinaryIO, chunk: bytes) -> bool:
        try:
            log_file.write(chunk)
            log_file.flush()
        except OSError as exc:
            # Close now: the chunk still buffered would make a later close fail again.
            with contextlib.suppress(OSError):
                log_file.close()
            _log.warning(
                "could not write %s.log (%s); output is no longer saved",
                self.stream_name,
                exc,
            )
            return False
        return True

    def _emit_lines(self, data: bytes) -> bytes:
        *lines, rest = data.split(b"\n")
        for line in lines:
            self._emit_text(line)
        if len(rest) > _MAX_LINE:
            # A process that never prints a newline must not grow this buffer.
            self._emit_text(rest)
            return b""
        return rest

    def _emit_text(self, raw: bytes) -> None:
        self.context.emit(raw.decode("utf-8", "replace").rstrip("\r"))

    def _write_final_status(self) -> None:
        try:
            (self.context.run_dir / "run.json").write_text(
                json.dumps(self.status(), indent=2, default=str), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            # A failing summary must not keep the session running.
            _log.exception("could not write run.json in %s", self.context.run_dir)

    def status(self) -> dict[str, Any]:
        """Return the run's state, times, exit code, command and summary.

        :return: the run summary
        :rtype: dict[str, Any]
        """
        finished = self._done.is_set()
        return {
            "state": "finished" if finished else "running",
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "exit_code": self._exit_code,
            "command": list(self._command.display) if self._command else [],
            **self.summary(
                self._exit_code if finished else None, cancelled=self._cancelled
            ),
        }

    def running_since(self) -> float | None:
        """Return when the process started, while it is still running.

        :return: start time, or None before start and after the end
        :rtype: float | None
        """
        if self._started_at is None or self._done.is_set():
            return None
        return self._started_at

    async def cancel(self) -> bool:
        """Ctrl-C the process group, then SIGTERM, then SIGKILL.

        A second call while the first is still escalating waits for it
        instead of signalling again: pytest treats a second Ctrl-C as "skip
        teardown".

        :return: False when nothing was running
        :rtype: bool
        """
        if self._process is None or self._done.is_set():
            return False
        if self._cancel_task is None:
            self._cancelled = True
            self._cancel_task = asyncio.create_task(self._escalate(self._process.pid))
        await asyncio.shield(self._cancel_task)
        return True

    async def _escalate(self, pid: int) -> None:
        grace = float(os.environ.get(CANCEL_GRACE_ENV, str(_DEFAULT_CANCEL_GRACE)))
        for sig, wait_for in (
            (signal.SIGINT, grace),
            (signal.SIGTERM, _TERM_GRACE),
            (signal.SIGKILL, _TERM_GRACE),
        ):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pid, sig)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._done.wait(), wait_for)
                return

    async def wait(self) -> None:
        """Return once the process has exited and its output is drained."""
        await self._done.wait()
