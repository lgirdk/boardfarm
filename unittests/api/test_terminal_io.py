"""Unit tests for the terminal fan-out."""

from __future__ import annotations

import asyncio
import threading

from boardfarm3.api.terminal_io import REASON_MAX_BYTES, Fanout, bound_reason


async def _drain(queue: asyncio.Queue[str | None]) -> list[str | None]:
    await asyncio.sleep(0.05)
    items: list[str | None] = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


async def test_fanout_delivers_to_all_subscribers() -> None:
    """Every subscriber receives every chunk."""
    fanout = Fanout(asyncio.get_running_loop())
    q1, q2 = fanout.subscribe(), fanout.subscribe()
    fanout.publish("a")
    fanout.publish("b")
    assert await _drain(q1) == ["a", "b"]
    assert await _drain(q2) == ["a", "b"]


async def test_fanout_unsubscribe_stops_delivery() -> None:
    """An unsubscribed queue receives nothing more."""
    fanout = Fanout(asyncio.get_running_loop())
    q1 = fanout.subscribe()
    fanout.unsubscribe(q1)
    fanout.publish("a")
    assert await _drain(q1) == []


async def test_fanout_slow_subscriber_drops_oldest_without_blocking() -> None:
    """A full queue drops its oldest chunks; the publisher never blocks."""
    fanout = Fanout(asyncio.get_running_loop(), maxsize=3)
    queue = fanout.subscribe()

    def produce() -> None:
        for i in range(10):
            fanout.publish(str(i))

    thread = threading.Thread(target=produce)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert await _drain(queue) == ["7", "8", "9"]


async def test_fanout_close_sends_sentinel() -> None:
    """Closing puts None on every queue."""
    fanout = Fanout(asyncio.get_running_loop())
    queue = fanout.subscribe()
    fanout.publish("a")
    fanout.close()
    assert await _drain(queue) == ["a", None]


def test_bound_reason_keeps_short_reasons() -> None:
    assert bound_reason("console closed") == "console closed"


def test_bound_reason_cuts_on_a_utf8_boundary() -> None:
    # 2-byte characters: 123 bytes would split the 62nd one.
    reason = "é" * 100
    bounded = bound_reason(reason)
    assert len(bounded.encode()) <= REASON_MAX_BYTES
    assert bounded == "é" * 61
    # 4-byte characters, after a 1-byte prefix.
    bounded = bound_reason("x" + "\U0001f600" * 40)
    assert len(bounded.encode()) <= REASON_MAX_BYTES
    assert bounded == "x" + "\U0001f600" * 30
