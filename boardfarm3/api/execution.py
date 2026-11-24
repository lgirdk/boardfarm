"""Single-worker execution queue bridging async FastAPI to blocking pexpect."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from boardfarm3.api.holds import ALL, ConsoleHeld, Holds

current_job_id: ContextVar[str | None] = ContextVar("current_job_id", default=None)
_log = logging.getLogger(__name__)

# Set on an exception by the queue, so an error raised by a sync job can still
# name the job that raised it.
JOB_ID_ATTR = "boardfarm_job_id"
MAX_PENDING_ENV = "BOARDFARM_MAX_QUEUED_JOBS"
_DEFAULT_MAX_PENDING = 100


class QueueFull(RuntimeError):
    """The queue already holds as many waiting jobs as it accepts."""


class JobCancelled(RuntimeError):
    """A sync job was cancelled while queued (e.g. by a session release)."""


class JobState(str, Enum):
    """Lifecycle states of a queued operation."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Job:  # pylint: disable=too-many-instance-attributes
    """One unit of work submitted to the execution queue."""

    id: str
    state: JobState = JobState.QUEUED
    result: Any = None
    error: BaseException | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    # Devices the job touches, or {ALL}; what holds are checked against.
    devices: frozenset[str] = frozenset({ALL})
    # True for the session release, which must run whatever is held.
    bypass_holds: bool = False


class ExecutionQueue:
    """FIFO queue running every operation on one worker thread.

    A single worker guarantees that no two operations touch a pexpect console
    at the same time. ``mode="async"`` therefore hands out a ticket, not
    concurrency.
    """

    def __init__(
        self,
        max_jobs: int = 200,
        max_pending: int | None = None,
        holds: Holds | None = None,
    ) -> None:
        """Initialise the queue.

        :param max_jobs: how many jobs to retain; only finished jobs are ever
            dropped to honour it
        :type max_jobs: int
        :param max_pending: how many jobs may wait to run before submit refuses;
            ``$BOARDFARM_MAX_QUEUED_JOBS`` (default 100) when omitted
        :type max_pending: int | None
        :param holds: device holds that refuse jobs; a fresh registry when omitted
        :type holds: Holds | None
        """
        self.holds = holds if holds is not None else Holds()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bf")
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._max_jobs = max_jobs
        self._max_pending = (
            max_pending
            if max_pending is not None
            else int(os.environ.get(MAX_PENDING_ENV, str(_DEFAULT_MAX_PENDING)))
        )
        self._running: Job | None = None
        # Guards the QUEUED->RUNNING and QUEUED->CANCELLED transitions so
        # cancel() and _run() can never race: whichever acquires the lock
        # first decides the job's fate. Never held while `func()` runs.
        self._lock = threading.Lock()

    def _record(self, job: Job) -> None:
        """Store a job, evicting the oldest *finished* jobs beyond the limit.

        A queued or running job is never evicted: its ticket must stay
        pollable until it ends.

        :param job: job to record
        :type job: Job
        """
        self._jobs[job.id] = job
        excess = len(self._jobs) - self._max_jobs
        if excess <= 0:
            return
        for job_id, old in list(self._jobs.items()):
            if excess <= 0:
                break
            if old.state in (JobState.DONE, JobState.ERROR, JobState.CANCELLED):
                del self._jobs[job_id]
                excess -= 1

    def _run(self, job: Job, func: Callable[[], Any]) -> Any:  # noqa: ANN401
        """Execute a job on the worker thread.

        :param job: job being executed
        :type job: Job
        :param func: callable to run
        :type func: Callable[[], Any]
        :raises ConsoleHeld: when a device the job touches was held after it
            was submitted
        :raises BaseException: whatever the callable raised
        :return: the callable's return value
        :rtype: Any
        """
        with self._lock:
            if job.state is JobState.CANCELLED:
                return None
            try:
                if not job.bypass_holds:
                    self.holds.check(job.devices)
            except ConsoleHeld as exc:
                job.state = JobState.ERROR
                job.error = exc
                job.finished_at = time.time()
                with contextlib.suppress(AttributeError):
                    setattr(exc, JOB_ID_ATTR, job.id)
                raise
            job.state = JobState.RUNNING
            job.started_at = time.time()
            self._running = job
        token = current_job_id.set(job.id)
        try:
            job.result = func()
        except BaseException as exc:
            job.state = JobState.ERROR
            job.error = exc
            job.finished_at = time.time()
            # Lets the HTTP error envelope name the job for a sync call too.
            with contextlib.suppress(AttributeError):
                setattr(exc, JOB_ID_ATTR, job.id)
            # Logged here so *every* job failure carries a traceback, not just
            # boot. current_job_id is still set, so ConsoleCapture attributes
            # the traceback to this job.
            _log.exception("job %s failed", job.id)
            raise
        else:
            job.state = JobState.DONE
            job.finished_at = time.time()
            return job.result
        finally:
            current_job_id.reset(token)
            with self._lock:
                self._running = None

    async def submit(
        self,
        func: Callable[[], Any],
        *,
        mode: str = "sync",
        on_done: Callable[[Job], None] | None = None,
        devices: frozenset[str] = frozenset({ALL}),
        bypass_holds: bool = False,
    ) -> Job:
        """Submit a callable to the worker thread.

        :param func: callable to run
        :type func: Callable[[], Any]
        :param mode: ``"sync"`` to await the result, ``"async"`` for a ticket
        :type mode: str
        :param on_done: called on the event loop once the job has finished,
            failed or been cancelled -- whether or not anyone still awaits it
        :type on_done: Callable[[Job], None] | None
        :param devices: device names the job touches; ``{ALL}`` when unknown
        :type devices: frozenset[str]
        :param bypass_holds: skip every hold check; only for the session release
        :type bypass_holds: bool
        :return: the job, completed when mode is ``"sync"``
        :rtype: Job
        :raises QueueFull: when ``max_pending`` jobs are already waiting
        :raises JobCancelled: when a sync job was cancelled before it ran
        :raises ConsoleHeld: when a device the job touches is held
        :raises asyncio.CancelledError: when the caller is cancelled while it
            awaits a sync job; a job that has not started yet is cancelled too

        # noqa: DAR401 cancelled
        # noqa: DAR402 ConsoleHeld JobCancelled
        """
        if not bypass_holds:
            self.holds.check(devices)
        with self._lock:
            waiting = sum(1 for j in self._jobs.values() if j.state is JobState.QUEUED)
        if waiting >= self._max_pending:
            msg = f"{waiting} jobs are already waiting to run; retry later"
            raise QueueFull(msg)
        job = Job(
            id=f"j-{uuid.uuid4().hex[:8]}",
            devices=devices,
            bypass_holds=bypass_holds,
        )
        self._record(job)
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._executor, self._run, job, func)
        if on_done is not None:
            future.add_done_callback(lambda _done: on_done(job))
        if mode == "async":
            # Retrieve the exception so asyncio does not warn that it was never
            # consumed; it is already recorded on the job.
            future.add_done_callback(
                lambda done: None if done.cancelled() else done.exception(),
            )
            return job
        try:
            await future
        except asyncio.CancelledError:
            # The caller went away. A job that has not started yet must not
            # stay "queued" forever; one already running cannot be stopped.
            self.cancel(job.id)
            raise
        if job.state is JobState.CANCELLED:
            # It never ran: an empty result would read as success.
            cancelled = JobCancelled(f"job {job.id} was cancelled before it ran")
            setattr(cancelled, JOB_ID_ATTR, job.id)
            raise cancelled
        return job

    def get(self, job_id: str) -> Job | None:
        """Look up a job by id.

        :param job_id: job identifier
        :type job_id: str
        :return: the job, or None if unknown or evicted
        :rtype: Job | None
        """
        return self._jobs.get(job_id)

    def running_job(self) -> Job | None:
        """Return the job currently executing, if any.

        :return: the running job, or None when the worker is idle
        :rtype: Job | None
        """
        return self._running

    async def wait_idle(self, devices: frozenset[str], poll: float = 0.05) -> None:
        """Wait until no running job touches any of *devices*.

        :param devices: device names to wait on; ``ALL`` matches every job
        :type devices: frozenset[str]
        :param poll: seconds between checks
        :type poll: float
        """
        while True:
            with self._lock:
                running = self._running
                busy = running is not None and (
                    ALL in devices
                    or ALL in running.devices
                    or not devices.isdisjoint(running.devices)
                )
            if not busy:
                return
            await asyncio.sleep(poll)

    def all_jobs(self) -> list[Job]:
        """Return every retained job, oldest first.

        :return: retained jobs in submission order
        :rtype: list[Job]
        """
        return list(self._jobs.values())

    def cancel(self, job_id: str) -> bool:
        """Cancel a job that has not started yet.

        A running job cannot be cancelled, because a pexpect ``expect()`` call
        cannot be safely interrupted.

        :param job_id: job identifier
        :type job_id: str
        :return: True when the job moved to CANCELLED
        :rtype: bool
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state is not JobState.QUEUED:
                return False
            job.state = JobState.CANCELLED
            job.finished_at = time.time()
            return True

    def cancel_pending(self) -> int:
        """Cancel every job that has not started yet.

        :return: how many jobs were cancelled
        :rtype: int
        """
        cancelled = 0
        with self._lock:
            for job in self._jobs.values():
                if job.state is JobState.QUEUED:
                    job.state = JobState.CANCELLED
                    job.finished_at = time.time()
                    cancelled += 1
        return cancelled

    def shutdown(self) -> None:
        """Shut the worker thread down, cancelling every job still waiting."""
        self.cancel_pending()
        self._executor.shutdown(wait=False, cancel_futures=True)
