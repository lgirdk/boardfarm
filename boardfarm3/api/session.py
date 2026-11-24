"""Session state machine for the boardfarm runtime agent."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from boardfarm3.api.console import ConsoleCapture, EventBuffer
from boardfarm3.api.errors import console_tail_from, error_envelope
from boardfarm3.api.execution import ExecutionQueue, Job, JobState
from boardfarm3.api.holds import Holds
from boardfarm3.api.logs import artifact_dir
from boardfarm3.api.modes import (
    INTERACT,
    ModeContext,
    ModeRequestError,
    boardfarm_argparser,
)
from boardfarm3.api.runtime import RuntimeContext
from boardfarm3.api.terminal import TerminalRegistry

if TYPE_CHECKING:
    from collections.abc import Mapping

    from boardfarm3.api.modes import SessionMode
    from boardfarm3.api.pyshell import PyShell
    from boardfarm3.api.runtime import RuntimeOptions

_log = logging.getLogger(__name__)


class SessionConflict(RuntimeError):
    """The request is not valid in the session's current state."""


class SessionState(str, Enum):
    """Lifecycle states of a runtime agent session."""

    CREATED = "created"
    CONFIGURED = "configured"
    BOOTING = "booting"
    READY = "ready"
    FAILED = "failed"
    RUNNING = "running"
    FINISHED = "finished"


# pylint: disable-next=too-many-instance-attributes
class Session:
    """One board, one runtime, one execution queue."""

    def __init__(
        self,
        session_id: str,
        options: RuntimeOptions,
        runtime: RuntimeContext | None = None,
        modes: Mapping[str, type[SessionMode]] | None = None,
    ) -> None:
        """Initialise the session.

        :param session_id: identifier assigned by the control plane
        :type session_id: str
        :param options: runtime options
        :type options: RuntimeOptions
        :param runtime: runtime context, built from options when omitted
        :type runtime: RuntimeContext | None
        :param modes: non-interactive modes this agent offers, by name
        :type modes: Mapping[str, type[SessionMode]] | None
        """
        self.session_id = session_id
        self.options = options
        self.runtime = runtime if runtime is not None else RuntimeContext(options)
        self.holds = Holds()
        self.queue = ExecutionQueue(holds=self.holds)
        self.terminals = TerminalRegistry(self.queue)
        # The Python shell, created on first open; dropped on release.
        self.pyshell: PyShell | None = None
        self.buffer = EventBuffer()
        self.capture = ConsoleCapture(self.buffer, log_dir=artifact_dir(session_id))
        self.capture.install()
        self.state = SessionState.CREATED
        self.created_at = time.time()
        self.last_activity = self.created_at
        self.error: dict[str, Any] | None = None
        self.payload: dict[str, Any] = {}
        self.modes: dict[str, type[SessionMode]] = dict(modes or {})
        self.mode = INTERACT
        self.run: SessionMode | None = None
        self._private_dir: Path | None = None
        self._boot_job: Job | None = None
        self._configuring = False

    @property
    def run_id(self) -> str:
        """Return the id the run's console lines carry as their job id.

        :return: ``run-<session_id>``
        :rtype: str
        """
        return f"run-{self.session_id}"

    def touch(self) -> None:
        """Record activity, so idle reaping can be added later."""
        self.last_activity = time.time()

    async def configure(
        self,
        payload: dict[str, Any],
        options: dict[str, Any] | None = None,
        *,
        mode: str = INTERACT,
        run: dict[str, Any] | None = None,
    ) -> None:
        """Apply options, then build devices (interact) or start the mode's run.

        :param payload: opaque session payload
        :type payload: dict[str, Any]
        :param options: overrides for the runtime options
        :type options: dict[str, Any] | None
        :param mode: ``interact`` or a mode from ``self.modes``
        :type mode: str
        :param run: the mode's request; required outside interact
        :type run: dict[str, Any] | None
        :raises SessionConflict: when the session was already configured
        :raises Exception: whatever building the devices or starting the run
            raised, once it is recorded as the session's error
        """
        # Once only: a second configure would build a new DeviceManager while
        # the first one's connections stay open.
        if self.state is not SessionState.CREATED or self._configuring:
            msg = f"cannot configure from state {self.state.value}"
            raise SessionConflict(msg)
        self._configuring = True
        try:
            self._check_mode(mode, run)
            if mode == INTERACT:
                await self._configure(payload, options)
            else:
                await self._start_mode(mode, payload, options, run or {})
        except Exception as exc:
            # A failed start already recorded its own error.
            if self.state is not SessionState.FAILED:
                self.error = error_envelope(exc, session_id=self.session_id)
            raise
        finally:
            self._configuring = False

    def _check_mode(self, mode: str, run: dict[str, Any] | None) -> None:
        if mode == INTERACT:
            if run is not None:
                msg = "run applies only to sessions in a non-interact mode"
                raise ModeRequestError(msg)
            return
        if mode not in self.modes:
            offered = ", ".join([INTERACT, *sorted(self.modes)])
            msg = f"unknown mode {mode!r}; this agent offers {offered}"
            raise ModeRequestError(msg)
        if run is None:
            msg = f"mode {mode} needs a run"
            raise ModeRequestError(msg)

    def _apply_options(
        self, options: dict[str, Any] | None, *, refresh: bool = True
    ) -> None:
        for field_name, value in (options or {}).items():
            if field_name == "save_console_logs" and not value:
                # Console logging is always on: an empty override redirects
                # nothing, it must not disable it.
                continue
            if field_name == "plugin_args":
                self.options.plugin_args.update(value)
            elif hasattr(self.options, field_name):
                setattr(self.options, field_name, value)
            else:
                self.options.plugin_args[field_name] = value
        if refresh:
            self.runtime.refresh_cmdline_args()

    async def _configure(
        self,
        payload: dict[str, Any],
        options: dict[str, Any] | None,
    ) -> None:
        self.payload = payload
        self._apply_options(options)

        def run() -> None:
            self.runtime.resolve(payload)
            self.runtime.register_devices()

        await self.queue.submit(run, mode="sync")
        self.state = SessionState.CONFIGURED
        self.touch()

    async def _start_mode(
        self,
        mode: str,
        payload: dict[str, Any],
        options: dict[str, Any] | None,
        run: dict[str, Any],
    ) -> None:
        self.payload = payload
        mode_class = self.modes[mode]
        stream_name = mode_class.stream_name

        def emit(line: str) -> None:
            # Through the capture, so the run's lines also reach its log file.
            self.capture.record(
                stream=stream_name, device=None, job_id=self.run_id, line=line
            )

        self._private_dir = Path(tempfile.mkdtemp(prefix="bf-run-"))
        try:
            handler = mode_class(
                ModeContext(
                    session_id=self.session_id,
                    board_name=self.options.board_name,
                    payload=payload,
                    options=dict(options or {}),
                    run=dict(run),
                    run_dir=artifact_dir(self.session_id) / "run",
                    private_dir=self._private_dir,
                    boardfarm_parser=boardfarm_argparser(
                        getattr(self.runtime, "plugin_manager", None)
                    ),
                    emit=emit,
                    finished=self._finish_run,
                )
            )
            handler.validate()
            # Only an accepted request may change the session's options: a
            # refused one must leave nothing behind for the retry to inherit.
            # A mode session never builds devices: its mode turns the options
            # into its own flags from ModeContext.options, so the synthesised
            # Namespace is not rebuilt.
            self._apply_options(options, refresh=False)
        except Exception:
            # A bad request or a crashing mode: either way nothing may be left
            # on disk, or a retry would orphan this directory.
            self._remove_private_dir()
            raise
        self.mode = mode
        try:
            await handler.start()
        except Exception as exc:
            self.state = SessionState.FAILED
            self.error = error_envelope(exc, session_id=self.session_id)
            self._remove_private_dir()
            raise
        self.run = handler
        self.state = SessionState.RUNNING
        # A retry that got this far no longer has a failure to report.
        self.error = None
        self.touch()

    def _finish_run(self) -> None:
        self.state = SessionState.FINISHED
        self._remove_private_dir()
        self.touch()

    def _remove_private_dir(self) -> None:
        if self._private_dir is not None:
            shutil.rmtree(self._private_dir, ignore_errors=True)
            self._private_dir = None

    async def boot(self) -> None:
        """Run the boot chain, moving the session to READY or FAILED.

        The outcome is applied by the job's completion callback, not by this
        coroutine: a caller that stops waiting (a client or proxy giving up on
        a sync boot) must not leave the session stuck in BOOTING.

        :raises SessionConflict: when the session runs in a non-interact mode
        :raises RuntimeError: when the session has not been configured
        """
        if self.mode != INTERACT:
            msg = f"boot() does not apply to a {self.mode} session"
            raise SessionConflict(msg)
        if self.state is not SessionState.CONFIGURED:
            msg = "configure() must succeed before boot()"
            raise RuntimeError(msg)
        self.state = SessionState.BOOTING
        self.touch()
        finished: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        def _on_done(job: Job) -> None:
            self._finish_boot(job)
            if not finished.done():
                finished.set_result(None)

        self._boot_job = await self.queue.submit(
            self.runtime.boot_blocking,
            mode="async",
            on_done=_on_done,
        )
        await asyncio.shield(finished)

    def _finish_boot(self, job: Job) -> None:
        if job.state is JobState.DONE:
            self.state = SessionState.READY
        else:
            # ERROR, or CANCELLED before it ever ran: either way not booted.
            failure = job.error or RuntimeError(
                f"boot job {job.id} was cancelled before it started",
            )
            self.state = SessionState.FAILED
            self.error = error_envelope(
                failure,
                session_id=self.session_id,
                job_id=job.id,
                console_tail=console_tail_from(self.buffer, job.id),
            )
        self.touch()

    async def release(self) -> None:
        """Cancel an active run, tear the runtime down and stop console capture.

        The run's private directory is removed too. A run that cannot be
        cancelled is logged, and the release goes on. Capture and the worker
        stop even when the runtime teardown fails.

        # noqa: DAR401
        # noqa: DAR402

        :raises Exception: whatever the runtime teardown raised
        """
        if self.run is not None:
            try:
                await self.run.cancel()
            except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                # A run that cannot be cancelled must not keep the runtime up.
                _log.exception(
                    "could not cancel the %s run of session %s; releasing anyway",
                    self.mode,
                    self.session_id,
                )
        self._remove_private_dir()
        status = (
            {"status": "success"}
            if self.state is SessionState.READY
            else {"status": "failed", "exception": self.error}
        )
        # Terminals first: their sockets close with 4410 and their holds go,
        # so nothing a human typed into can outlive the runtime.
        await self.terminals.close_all()
        # The Python shell too: its sockets close with 4410, its REPL ends,
        # its ALL hold goes and its namespace is dropped.
        if self.pyshell is not None:
            shell, self.pyshell = self.pyshell, None
            await shell.close_all()
        # Release runs right after the job in progress, not after a backlog
        # of work that nobody will collect.
        self.queue.cancel_pending()
        try:
            # Bypasses holds: a held device must not keep the runtime from
            # tearing down.
            await self.queue.submit(
                lambda: self.runtime.release(status),
                mode="sync",
                bypass_holds=True,
            )
        finally:
            # A failed teardown still ends capture and the worker: nothing
            # retries the release.
            self.capture.uninstall()
            self.queue.shutdown()

    def liveness(self) -> dict[str, Any]:
        """Report progress evidence for the running job.

        ``quiet`` means only "no output for a while" and is reversible — one
        more log line clears it. It is deliberately advisory: no code branches
        on it, because a silent image flash and a wedged expect() are
        indistinguishable by idle time alone. Use ``GET /diagnostics/threads``
        to tell them apart.

        :return: liveness evidence
        :rtype: dict[str, Any]
        """
        last_ts = self.buffer.last_event_ts
        last_line = self.buffer.last_line
        running = self.queue.running_job()
        started = running.started_at if running is not None else None
        if started is None and self.run is not None:
            started = self.run.running_since()
        if started is None:
            return {
                "quiet": False,
                "running_for": None,
                "idle_for": None,
                "last_line": last_line,
                "last_event_ts": last_ts,
            }
        now = time.time()
        idle_for = now - max(started, last_ts)
        return {
            "quiet": idle_for > self.options.quiet_after,
            "running_for": now - started,
            "idle_for": idle_for,
            "last_line": last_line,
            "last_event_ts": last_ts,
        }

    def status(self) -> dict[str, Any]:
        """Return the session status the control plane surfaces.

        :return: session status
        :rtype: dict[str, Any]
        """
        return {
            "session_id": self.session_id,
            "board_name": self.options.board_name,
            "state": self.state.value,
            "liveness": self.liveness(),
            # True only after a full boot sequence completed (skip_boot=False)
            "booted": self.state is SessionState.READY and not self.options.skip_boot,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "error": self.error,
            "boot_job_id": self._boot_job.id if self._boot_job is not None else None,
            "mode": self.mode,
            "run": self.run.status() if self.run is not None else None,
        }
