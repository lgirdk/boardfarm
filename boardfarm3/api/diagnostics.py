"""Thread-stack sampling for distinguishing a wedged agent from a slow one."""

from __future__ import annotations

import sys
import threading
import time
import traceback
from typing import Any

# ThreadPoolExecutor in ExecutionQueue uses thread_name_prefix="bf", so its
# worker is named "bf_0". That thread is the one blocked in pexpect.
_WORKER_PREFIX = "bf"


def thread_snapshot() -> dict[str, Any]:
    """Capture the stack of every live thread.

    Read-only and allocation-light, so it is safe to call against a session
    whose worker thread is wedged. Two snapshots taken 30 s apart, diffed,
    distinguish a blocked ``expect()`` from a healthy long wait.

    :return: snapshot with a capture timestamp and one entry per thread
    :rtype: dict[str, Any]
    """
    frames = sys._current_frames()  # noqa: SLF001
    threads: list[dict[str, Any]] = [
        {
            "name": thread.name,
            "ident": thread.ident,
            "worker": thread.name.startswith(_WORKER_PREFIX),
            "daemon": thread.daemon,
            "stack": (
                traceback.format_stack(frames[thread.ident])
                if thread.ident in frames
                else []
            ),
        }
        for thread in threading.enumerate()
    ]
    return {"captured_at": time.time(), "threads": threads}


def format_threads(snapshot: dict[str, Any]) -> str:
    """Render a snapshot as plain text for the diagnostics bundle.

    :param snapshot: output of :func:`thread_snapshot`
    :type snapshot: dict[str, Any]
    :return: human-readable stack dump
    :rtype: str
    """
    lines = [f"captured_at: {snapshot['captured_at']}", ""]
    for thread in snapshot["threads"]:
        marker = " [WORKER]" if thread["worker"] else ""
        lines.append(f"--- {thread['name']} (ident={thread['ident']}){marker}")
        lines.extend(frame.rstrip() for frame in thread["stack"])
        lines.append("")
    return "\n".join(lines)
