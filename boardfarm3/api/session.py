"""Session state machine for the boardfarm runtime agent."""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import TYPE_CHECKING, Any

from boardfarm3.api.console import ConsoleCapture, EventBuffer
from boardfarm3.api.errors import console_tail_from, error_envelope
from boardfarm3.api.execution import ExecutionQueue
from boardfarm3.api.runtime import RuntimeContext

if TYPE_CHECKING:
    from boardfarm3.api.runtime import RuntimeOptions


class SessionState(str, Enum):
    """Lifecycle states of a runtime agent session."""

    CREATED = "created"
    CONFIGURED = "configured"
    BOOTING = "booting"
    READY = "ready"
    FAILED = "failed"
    STUCK = "stuck"


# pylint: disable-next=too-many-instance-attributes
class Session:
    """One board, one runtime, one execution queue."""

    def __init__(
        self,
        session_id: str,
        options: RuntimeOptions,
        runtime: RuntimeContext | None = None,
        stuck_after: float = 900.0,
    ) -> None:
        """Initialise the session.

        :param session_id: identifier assigned by the control plane
        :type session_id: str
        :param options: runtime options
        :type options: RuntimeOptions
        :param runtime: runtime context, built from options when omitted
        :type runtime: RuntimeContext | None
        :param stuck_after: seconds a running job may take before the session
            is reported as stuck
        :type stuck_after: float
        """
        self.session_id = session_id
        self.options = options
        self.stuck_after = stuck_after
        self.runtime = runtime if runtime is not None else RuntimeContext(options)
        self.queue = ExecutionQueue()
        self.buffer = EventBuffer()
        self.capture = ConsoleCapture(self.buffer)
        self.capture.install()
        self.state = SessionState.CREATED
        self.created_at = time.time()
        self.last_activity = self.created_at
        self.error: dict[str, Any] | None = None

    def touch(self) -> None:
        """Record activity, so idle reaping can be added later."""
        self.last_activity = time.time()

    async def configure(
        self,
        payload: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> None:
        """Apply options, resolve the payload and register devices.

        Runs on the worker thread so device construction is serialised with
        everything else.

        :param payload: opaque session payload
        :type payload: dict[str, Any]
        :param options: overrides for the runtime options
        :type options: dict[str, Any] | None
        """
        for field_name, value in (options or {}).items():
            if hasattr(self.options, field_name):
                setattr(self.options, field_name, value)
        self.runtime.refresh_cmdline_args()

        def run() -> None:
            self.runtime.resolve(payload)
            self.runtime.register_devices()

        await self.queue.submit(run, mode="sync")
        self.state = SessionState.CONFIGURED
        self.touch()

    async def boot(self) -> None:
        """Run the boot chain, moving the session to READY or FAILED.

        :raises RuntimeError: when the session has not been configured
        """
        if self.state is not SessionState.CONFIGURED:
            msg = "configure() must succeed before boot()"
            raise RuntimeError(msg)
        self.state = SessionState.BOOTING
        self.touch()
        job = await self.queue.submit(self.runtime.boot_blocking, mode="async")
        while job.state.value in ("queued", "running"):  # noqa: ASYNC110
            await asyncio.sleep(0.05)
        if job.error is not None:
            self.state = SessionState.FAILED
            self.error = error_envelope(
                job.error,
                session_id=self.session_id,
                job_id=job.id,
                console_tail=console_tail_from(self.buffer, job.id),
            )
        else:
            self.state = SessionState.READY
        self.touch()

    async def release(self) -> None:
        """Tear the runtime down and stop console capture."""
        status = (
            {"status": "success"}
            if self.state is SessionState.READY
            else {"status": "failed", "exception": self.error}
        )
        await self.queue.submit(lambda: self.runtime.release(status), mode="sync")
        self.capture.uninstall()
        self.queue.shutdown()

    def is_stuck(self) -> bool:
        """Report whether a job has been running past the watchdog threshold.

        A wedged pexpect console blocks the single worker, so this is the
        signal that the session must be deleted and recreated.

        :return: True when the running job has exceeded ``stuck_after``
        :rtype: bool
        """
        running = self.queue.running_job()
        if running is None or running.started_at is None:
            return False
        return (time.time() - running.started_at) > self.stuck_after

    def status(self) -> dict[str, Any]:
        """Return the session status the control plane surfaces.

        :return: session status
        :rtype: dict[str, Any]
        """
        state = SessionState.STUCK.value if self.is_stuck() else self.state.value
        return {
            "session_id": self.session_id,
            "board_name": self.options.board_name,
            "state": state,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "error": self.error,
        }
