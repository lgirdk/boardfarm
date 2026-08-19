"""Thread-stack snapshot: the evidence that separates wedged from slow."""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.diagnostics import format_threads, thread_snapshot

HTTP_OK = 200


def test_snapshot_includes_the_current_thread() -> None:
    snapshot = thread_snapshot()
    names = [thread["name"] for thread in snapshot["threads"]]
    assert threading.current_thread().name in names
    assert snapshot["captured_at"] > 0


def test_snapshot_flags_the_execution_worker() -> None:
    """The worker thread is the one that matters; it must be identifiable."""
    started = threading.Event()
    release = threading.Event()

    def block() -> None:
        started.set()
        release.wait(timeout=5)

    worker = threading.Thread(target=block, name="bf_0", daemon=True)
    worker.start()
    started.wait(timeout=5)
    try:
        snapshot = thread_snapshot()
        workers = [t for t in snapshot["threads"] if t["worker"]]
        assert len(workers) == 1
        assert workers[0]["name"] == "bf_0"
        assert any("block" in frame for frame in workers[0]["stack"])
    finally:
        release.set()
        worker.join(timeout=5)


def test_format_threads_is_readable_text() -> None:
    text = format_threads(thread_snapshot())
    assert "captured_at" in text
    assert threading.current_thread().name in text


def test_threads_route_returns_stacks() -> None:
    app = app_module.create_app("s-test", "board")
    with TestClient(app) as client:
        response = client.get("/diagnostics/threads")
    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["threads"]
    assert all("stack" in thread for thread in body["threads"])
