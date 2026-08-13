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
