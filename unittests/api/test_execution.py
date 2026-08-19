"""Unit tests for the boardfarm API execution queue."""

import asyncio
import gc
import logging
import threading
import time

import pytest

from boardfarm3.api.execution import ExecutionQueue, JobState, current_job_id


@pytest.fixture(name="queue")
def queue_fixture() -> ExecutionQueue:
    """Build an execution queue and shut it down afterwards.

    :yield: execution queue
    :rtype: ExecutionQueue
    """
    execution_queue = ExecutionQueue()
    yield execution_queue
    execution_queue.shutdown()


@pytest.mark.asyncio
async def test_sync_mode_returns_completed_job(queue: ExecutionQueue) -> None:
    """A sync submission runs to completion before returning.

    :param queue: execution queue
    :type queue: ExecutionQueue
    """
    job = await queue.submit(lambda: 21 * 2, mode="sync")
    assert job.state is JobState.DONE
    assert job.result == 42


@pytest.mark.asyncio
async def test_async_mode_returns_immediately(queue: ExecutionQueue) -> None:
    """An async submission returns before the callable finishes.

    :param queue: execution queue
    :type queue: ExecutionQueue
    """
    job = await queue.submit(
        lambda: time.sleep(0.2) or "late",  # noqa: ASYNC251
        mode="async",
    )
    assert job.state in (JobState.QUEUED, JobState.RUNNING)
    await asyncio.sleep(0.4)
    assert queue.get(job.id).state is JobState.DONE
    assert queue.get(job.id).result == "late"


@pytest.mark.asyncio
async def test_jobs_are_serialised_in_submission_order(queue: ExecutionQueue) -> None:
    """Async jobs queue behind each other; nothing runs concurrently.

    Submission order alone is not proof of serialisation: five callables that
    all sleep for the same duration tend to wake (and thus append to
    ``order``) in submission order even when a thread pool runs them in
    parallel. ``peak`` is the real assertion -- it can only reach 1 if the
    callables' execution windows never overlap.

    :param queue: execution queue
    :type queue: ExecutionQueue
    """
    order: list[int] = []
    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def make(index: int) -> object:
        def run() -> None:
            nonlocal in_flight, peak
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
            order.append(index)

        return run

    jobs = [await queue.submit(make(index), mode="async") for index in range(5)]
    while any(  # noqa: ASYNC110
        queue.get(job.id).state is not JobState.DONE for job in jobs
    ):
        await asyncio.sleep(0.02)
    assert order == [0, 1, 2, 3, 4]
    assert peak == 1


@pytest.mark.asyncio
async def test_exception_is_captured_on_the_job(
    queue: ExecutionQueue,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A raising callable marks the job ERROR and stores the exception.

    Also guards the async done-callback's exception consumption directly:
    ``-W error::RuntimeWarning`` does NOT catch a regression here, because
    asyncio reports an unretrieved future exception through the ``asyncio``
    logger (``Future.__del__`` -> ``logging``), never through
    ``warnings.warn``. Checking ``caplog`` is the real guard.

    :param queue: execution queue
    :type queue: ExecutionQueue
    :param caplog: pytest log capture fixture
    :type caplog: pytest.LogCaptureFixture
    """

    def boom() -> None:
        msg = "device exploded"
        raise ValueError(msg)

    job = await queue.submit(boom, mode="async")
    while queue.get(job.id).state not in (  # noqa: ASYNC110
        JobState.DONE,
        JobState.ERROR,
    ):
        await asyncio.sleep(0.02)
    assert queue.get(job.id).state is JobState.ERROR
    assert str(queue.get(job.id).error) == "device exploded"
    # The wrapped future completes (and its done-callback runs) one event
    # loop turn after job.state flips; give it a moment before collecting.
    await asyncio.sleep(0.05)
    gc.collect()
    assert "never retrieved" not in caplog.text


@pytest.mark.asyncio
async def test_sync_mode_reraises(queue: ExecutionQueue) -> None:
    """Sync submissions propagate the exception to the caller.

    :param queue: execution queue
    :type queue: ExecutionQueue
    """

    def boom() -> None:
        msg = "device exploded"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="device exploded"):
        await queue.submit(boom, mode="sync")


@pytest.mark.asyncio
async def test_job_id_is_visible_to_the_running_callable(
    queue: ExecutionQueue,
) -> None:
    """The worker sets current_job_id so log records can be attributed.

    :param queue: execution queue
    :type queue: ExecutionQueue
    """
    seen: list[str | None] = []
    job = await queue.submit(lambda: seen.append(current_job_id.get()), mode="sync")
    assert seen == [job.id]


@pytest.mark.asyncio
async def test_queued_job_can_be_cancelled(queue: ExecutionQueue) -> None:
    """A job still queued behind a slow one can be cancelled.

    :param queue: execution queue
    :type queue: ExecutionQueue
    """
    await queue.submit(lambda: time.sleep(0.3), mode="async")  # noqa: ASYNC251
    second = await queue.submit(lambda: "never", mode="async")
    assert queue.cancel(second.id) is True
    assert queue.get(second.id).state is JobState.CANCELLED


@pytest.mark.asyncio
async def test_running_job_is_reported_then_cleared(queue: ExecutionQueue) -> None:
    """running_job() exposes the in-flight job, for the stuck watchdog.

    :param queue: execution queue
    :type queue: ExecutionQueue
    """
    assert queue.running_job() is None
    job = await queue.submit(lambda: time.sleep(0.3), mode="async")  # noqa: ASYNC251
    await asyncio.sleep(0.1)
    running = queue.running_job()
    assert running is not None
    assert running.id == job.id
    assert running.started_at is not None
    await asyncio.sleep(0.4)
    assert queue.running_job() is None


@pytest.mark.asyncio
async def test_job_store_is_bounded(queue: ExecutionQueue) -> None:  # noqa: ARG001
    """Only the most recent jobs are retained.

    :param queue: execution queue
    :type queue: ExecutionQueue
    """
    small = ExecutionQueue(max_jobs=3)
    try:
        jobs = [await small.submit(lambda: None, mode="sync") for _ in range(5)]
        assert small.get(jobs[0].id) is None
        assert small.get(jobs[-1].id) is not None
    finally:
        small.shutdown()


@pytest.mark.asyncio
async def test_job_failure_is_logged_with_a_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every job failure must be logged, not only boot.

    :param caplog: pytest log capture fixture
    :type caplog: pytest.LogCaptureFixture
    """
    queue = ExecutionQueue()

    def boom() -> None:
        msg = "kaboom"
        raise ValueError(msg)

    with caplog.at_level(logging.DEBUG, logger="boardfarm3.api.execution"):
        await queue.submit(boom, mode="async")
        await asyncio.sleep(0.2)

    assert any(record.exc_info for record in caplog.records)
    assert "kaboom" in caplog.text
    queue.shutdown()


@pytest.mark.asyncio
async def test_all_jobs_returns_every_retained_job() -> None:
    """The bundle needs to enumerate jobs without touching private state."""
    queue = ExecutionQueue()
    await queue.submit(lambda: 1, mode="sync")
    await queue.submit(lambda: 2, mode="sync")
    jobs = queue.all_jobs()
    assert len(jobs) == 2
    assert [job.result for job in jobs] == [1, 2]
    queue.shutdown()
