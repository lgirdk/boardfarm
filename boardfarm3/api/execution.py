"""Single-worker execution queue bridging async FastAPI to blocking pexpect."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

current_job_id: ContextVar[str | None] = ContextVar("current_job_id", default=None)


class JobState(str, Enum):
    """Lifecycle states of a queued operation."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """One unit of work submitted to the execution queue."""

    id: str
    state: JobState = JobState.QUEUED
    result: Any = None
    error: BaseException | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None


class ExecutionQueue:
    """FIFO queue running every operation on one worker thread.

    A single worker guarantees that no two operations touch a pexpect console
    at the same time. ``mode="async"`` therefore hands out a ticket, not
    concurrency.
    """

    def __init__(self, max_jobs: int = 200) -> None:
        """Initialise the queue.

        :param max_jobs: how many finished jobs to retain
        :type max_jobs: int
        """
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bf")
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._max_jobs = max_jobs
        self._running: Job | None = None
        # Guards the QUEUED->RUNNING and QUEUED->CANCELLED transitions so
        # cancel() and _run() can never race: whichever acquires the lock
        # first decides the job's fate. Never held while `func()` runs.
        self._lock = threading.Lock()

    def _record(self, job: Job) -> None:
        """Store a job, evicting the oldest beyond the retention limit.

        :param job: job to record
        :type job: Job
        """
        self._jobs[job.id] = job
        while len(self._jobs) > self._max_jobs:
            self._jobs.popitem(last=False)

    def _run(self, job: Job, func: Callable[[], Any]) -> Any:  # noqa: ANN401
        """Execute a job on the worker thread.

        :param job: job being executed
        :type job: Job
        :param func: callable to run
        :type func: Callable[[], Any]
        :raises BaseException: whatever the callable raised
        :return: the callable's return value
        :rtype: Any
        """
        with self._lock:
            if job.state is JobState.CANCELLED:
                return None
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
    ) -> Job:
        """Submit a callable to the worker thread.

        :param func: callable to run
        :type func: Callable[[], Any]
        :param mode: ``"sync"`` to await the result, ``"async"`` for a ticket
        :type mode: str
        :return: the job, completed when mode is ``"sync"``
        :rtype: Job
        """
        job = Job(id=f"j-{uuid.uuid4().hex[:8]}")
        self._record(job)
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._executor, self._run, job, func)
        if mode == "async":
            # Retrieve the exception so asyncio does not warn that it was never
            # consumed; it is already recorded on the job.
            future.add_done_callback(
                lambda done: None if done.cancelled() else done.exception(),
            )
            return job
        await future
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

    def shutdown(self) -> None:
        """Shut the worker thread down."""
        self._executor.shutdown(wait=False, cancel_futures=True)
