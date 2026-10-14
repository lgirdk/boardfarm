"""Unit tests for boardfarm API console capture."""

import asyncio
import logging

import pytest

from boardfarm3.api.console import ConsoleCapture, EventBuffer
from boardfarm3.api.execution import current_job_id


@pytest.fixture(name="buffer")
def buffer_fixture() -> EventBuffer:
    """Build an event buffer.

    :return: event buffer
    :rtype: EventBuffer
    """
    return EventBuffer()


@pytest.fixture(name="capture")
def capture_fixture(buffer: EventBuffer) -> ConsoleCapture:
    """Install console capture and remove it afterwards.

    :param buffer: event buffer
    :type buffer: EventBuffer
    :yield: console capture
    :rtype: ConsoleCapture
    """
    console_capture = ConsoleCapture(buffer)
    console_capture.install()
    yield console_capture
    console_capture.uninstall()


def test_console_record_is_attributed_to_its_device(
    buffer: EventBuffer,
    capture: ConsoleCapture,  # noqa: ARG001
) -> None:
    """A pexpect.<device>.console record yields stream=console and the device.

    :param buffer: event buffer
    :type buffer: EventBuffer
    :param capture: installed console capture
    :type capture: ConsoleCapture
    """
    logging.getLogger("pexpect.lan.console").debug("BOOTP broadcast 1")
    events, _ = buffer.read()
    assert len(events) == 1
    assert events[0].stream == "console"
    assert events[0].device == "lan"
    assert events[0].line == "BOOTP broadcast 1"


def test_framework_record_has_no_device(
    buffer: EventBuffer,
    capture: ConsoleCapture,  # noqa: ARG001
) -> None:
    """A boardfarm3.* record is captured as the framework stream.

    :param buffer: event buffer
    :type buffer: EventBuffer
    :param capture: installed console capture
    :type capture: ConsoleCapture
    """
    logging.getLogger("boardfarm3.plugins.core").info("registering devices")
    events, _ = buffer.read()
    assert events[0].stream == "framework"
    assert events[0].device is None


def test_records_are_tagged_with_the_current_job(
    buffer: EventBuffer,
    capture: ConsoleCapture,  # noqa: ARG001
) -> None:
    """Console lines produced during a job carry that job's id.

    :param buffer: event buffer
    :type buffer: EventBuffer
    :param capture: installed console capture
    :type capture: ConsoleCapture
    """
    token = current_job_id.set("j-abc123")
    try:
        logging.getLogger("pexpect.board.console").debug("login:")
    finally:
        current_job_id.reset(token)
    events, _ = buffer.read()
    assert events[0].job_id == "j-abc123"


def test_read_filters_and_advances_cursor(buffer: EventBuffer) -> None:
    """Reading filters by device and returns the next cursor.

    :param buffer: event buffer
    :type buffer: EventBuffer
    """
    buffer.append(stream="console", device="lan", job_id=None, line="one")
    buffer.append(stream="console", device="wan", job_id=None, line="two")
    buffer.append(stream="console", device="lan", job_id=None, line="three")
    events, cursor = buffer.read(device="lan")
    assert [event.line for event in events] == ["one", "three"]
    assert cursor == 3
    later, _ = buffer.read(cursor=cursor)
    assert later == []


def test_read_filters_by_job_id(buffer: EventBuffer) -> None:
    """Per-call console retrieval returns only that job's lines.

    :param buffer: event buffer
    :type buffer: EventBuffer
    """
    buffer.append(stream="console", device="lan", job_id="j-1", line="a")
    buffer.append(stream="console", device="lan", job_id="j-2", line="b")
    events, _ = buffer.read(job_id="j-2")
    assert [event.line for event in events] == ["b"]


def test_capture_stops_console_reaching_stdout(capture: ConsoleCapture) -> None:  # noqa: ARG001
    """Propagation is disabled so console traffic never floods agent stdout.

    :param capture: installed console capture
    :type capture: ConsoleCapture
    """
    assert logging.getLogger("pexpect").propagate is False


def test_uninstall_restores_logger_state(buffer: EventBuffer) -> None:
    """Uninstalling removes handlers and restores propagation.

    :param buffer: event buffer
    :type buffer: EventBuffer
    """
    console_capture = ConsoleCapture(buffer)
    console_capture.install()
    console_capture.uninstall()
    assert logging.getLogger("pexpect").propagate is True
    logging.getLogger("pexpect.lan.console").debug("ignored")
    events, _ = buffer.read()
    assert events == []


def test_read_cursor_stays_correct_after_the_buffer_wraps() -> None:
    """The cursor is a sequence number, not a deque index.

    Once ``maxlen`` is exceeded, the oldest events are evicted from the
    deque and every remaining event shifts position. A ``read()`` that keyed
    off list position instead of each event's own ``seq`` would silently
    return the wrong events after this happens.
    """
    small_buffer = EventBuffer(maxlen=3)
    for index in range(5):
        small_buffer.append(
            stream="console",
            device="lan",
            job_id=None,
            line=str(index),
        )
    events, cursor = small_buffer.read()
    assert [event.line for event in events] == ["2", "3", "4"]
    assert [event.seq for event in events] == [2, 3, 4]
    assert cursor == 5
    # A cursor referring to an already-evicted sequence number must not
    # error, and must not be misinterpreted as a deque index -- it simply
    # returns whatever of the requested range still remains.
    events, cursor = small_buffer.read(cursor=0)
    assert [event.line for event in events] == ["2", "3", "4"]
    assert cursor == 5
    # A cursor inside the retained range still filters correctly.
    events, cursor = small_buffer.read(cursor=3)
    assert [event.line for event in events] == ["3", "4"]
    assert cursor == 5


@pytest.mark.asyncio
async def test_subscribe_removes_queue_when_consumer_disconnects(
    buffer: EventBuffer,
) -> None:
    """An abandoned subscriber's queue is removed, not leaked forever.

    ``append()`` writes to every subscriber queue unconditionally, so an SSE
    client that disconnects without the generator's ``finally`` running
    would leave a queue behind that grows forever.

    :param buffer: event buffer
    :type buffer: EventBuffer
    """
    subscriber = buffer.subscribe()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(subscriber.__anext__(), timeout=0.01)
    assert not buffer._subscribers


def test_read_cursor_after_limit_truncation_has_no_gap_or_duplicate(
    buffer: EventBuffer,
) -> None:
    """A limit-truncated read's cursor must resume the scan, not the tail.

    Regression test: ``read()`` used to return ``self._next_seq`` (the
    buffer's global append-tail) as the next cursor even when the scan
    stopped early because ``limit`` was hit, so a client polling
    ``read(cursor=<returned>)`` would skip every event between the
    truncation point and the tail. Draining the buffer through a small
    limit must recover every event exactly once, in order.

    :param buffer: event buffer
    :type buffer: EventBuffer
    """
    for index in range(25):
        buffer.append(stream="console", device="lan", job_id=None, line=str(index))
    collected: list[int] = []
    cursor = 0
    while True:
        events, cursor = buffer.read(cursor=cursor, limit=10)
        if not events:
            break
        collected.extend(event.seq for event in events)
    assert collected == list(range(25))
    assert len(collected) == len(set(collected))


def test_read_cursor_after_limit_truncation_with_device_filter(
    buffer: EventBuffer,
) -> None:
    """Filtering plus a truncating limit must not lose or duplicate events.

    The truncation-aware cursor must resume the scan immediately after the
    last *selected* event, skipping over any non-matching events in
    between on the next call -- not just re-scan from the buffer's tail.

    :param buffer: event buffer
    :type buffer: EventBuffer
    """
    for index in range(30):
        device = "lan" if index % 2 == 0 else "wan"
        buffer.append(stream="console", device=device, job_id=None, line=str(index))
    expected = [index for index in range(30) if index % 2 == 0]
    collected: list[int] = []
    cursor = 0
    while True:
        events, cursor = buffer.read(cursor=cursor, device="lan", limit=3)
        if not events:
            break
        collected.extend(event.seq for event in events)
    assert collected == expected
    assert len(collected) == len(set(collected))


def test_install_is_idempotent(buffer: EventBuffer) -> None:
    """A second install() without an intervening uninstall() must be inert.

    Regression test: ``install()`` used to unconditionally overwrite
    ``_previous_propagate`` and re-append the handler on every call. A
    second ``install()`` therefore snapshotted the *already-modified*
    propagate value (``False``), so a later single ``uninstall()``
    "restored" ``False`` -- leaving console traffic permanently suppressed
    for the rest of the process.

    :param buffer: event buffer
    :type buffer: EventBuffer
    """
    console_capture = ConsoleCapture(buffer)
    console_capture.install()
    console_capture.install()
    pexpect_logger = logging.getLogger("pexpect")
    assert pexpect_logger.handlers.count(console_capture) == 1
    console_capture.uninstall()
    assert pexpect_logger.propagate is True


def test_capture_preserves_exception_tracebacks() -> None:
    """record.getMessage() drops exc_info, which loses every traceback."""
    buffer = EventBuffer()
    capture = ConsoleCapture(buffer)
    capture.install()
    try:
        logger = logging.getLogger("boardfarm3.test")
        try:
            msg = "kaboom"
            raise ValueError(msg)  # noqa: TRY301
        except ValueError:
            logger.exception("job failed")
    finally:
        capture.uninstall()

    events, _ = buffer.read()
    joined = "\n".join(event.line for event in events)
    assert "job failed" in joined
    assert "ValueError: kaboom" in joined
    assert "Traceback" in joined


# -- the buffer is written from the pexpect worker thread ---------------------
#
# Console lines are appended on the ``bf`` worker thread while HTTP handlers
# read on the event loop thread. Both sides must be safe against the other.


def test_read_is_safe_while_the_worker_thread_appends() -> None:
    """A full read never fails because the worker appended mid-scan."""
    import threading
    import time

    buffer = EventBuffer(maxlen=20_000)
    for index in range(20_000):
        buffer.append(stream="console", device="board", job_id=None, line=str(index))
    stop = threading.Event()

    def writer() -> None:
        while not stop.is_set():
            buffer.append(stream="console", device="board", job_id=None, line="y")

    thread = threading.Thread(target=writer)
    thread.start()
    errors: list[Exception] = []
    deadline = time.monotonic() + 2.0
    try:
        while time.monotonic() < deadline:
            try:
                buffer.read(cursor=0, device="nobody", limit=1000)
            except RuntimeError as exc:  # noqa: PERF203  # deque mutated during iteration
                errors.append(exc)
    finally:
        stop.set()
        thread.join()
    assert errors == []


@pytest.mark.asyncio
async def test_live_subscriber_is_woken_promptly_by_a_worker_thread_append() -> None:
    """A line logged on the worker thread reaches an idle SSE subscriber at once."""
    import threading
    import time

    buffer = EventBuffer()
    async with buffer.subscription() as queue:
        threading.Timer(
            0.05,
            lambda: buffer.append(
                stream="console", device="board", job_id=None, line="hello"
            ),
        ).start()
        started = time.monotonic()
        event = await asyncio.wait_for(queue.get(), timeout=3.0)
        elapsed = time.monotonic() - started
    assert event.line == "hello"
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_slow_subscriber_keeps_only_the_newest_events() -> None:
    """A subscriber that stops reading cannot grow memory without bound."""
    buffer = EventBuffer(subscriber_limit=100)
    async with buffer.subscription() as queue:
        for index in range(1_000):
            buffer.append(stream="console", device="b", job_id=None, line=str(index))
        await asyncio.sleep(0)
        assert queue.qsize() == 100
        kept = [queue.get_nowait() for _ in range(100)]
    assert [event.line for event in kept] == [str(i) for i in range(900, 1_000)]


def test_a_bad_log_call_never_raises_into_device_code(
    capture: ConsoleCapture,
) -> None:
    """A malformed log call in device code must not fail the job that made it.

    Driven through the handler directly: pytest's own capture handler
    deliberately re-raises bad log calls, which would mask ours.
    """
    record = logging.LogRecord(
        name="boardfarm3.devices.demo",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="%s and %s",
        args=("only-one",),
        exc_info=None,
    )
    capture.handle(record)


def test_negative_cursor_tails_the_matching_events(buffer: EventBuffer) -> None:
    """``cursor=-N`` with a device filter returns that device's last N lines."""
    for device in ("lan", "wan", "lan", "wan", "wan"):
        buffer.append(stream="console", device=device, job_id=None, line=device)
    events, _ = buffer.read(cursor=-2, device="lan")
    assert [event.seq for event in events] == [0, 2]
