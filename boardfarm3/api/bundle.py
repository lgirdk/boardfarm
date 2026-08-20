"""Assembly of the agent diagnostics bundle."""

from __future__ import annotations

import io
import json
import tarfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from boardfarm3 import __version__
from boardfarm3.api.diagnostics import format_threads, thread_snapshot
from boardfarm3.api.errors import error_envelope
from boardfarm3.api.redact import redact

if TYPE_CHECKING:
    from boardfarm3.api.session import Session

_REDACTED_MEMBERS = ["session.json", "config.json"]


def _add_text(archive: tarfile.TarFile, name: str, text: str) -> None:
    """Add an in-memory string to the archive as a file.

    :param archive: open tar archive
    :type archive: tarfile.TarFile
    :param name: member name inside the archive
    :type name: str
    :param text: file contents
    :type text: str
    """
    data = text.encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = int(time.time())
    archive.addfile(info, io.BytesIO(data))


def _jobs_payload(session: Session) -> list[dict[str, Any]]:
    """Serialise every retained job, with tracebacks for failures.

    :param session: session whose queue to enumerate
    :type session: Session
    :return: one entry per retained job
    :rtype: list[dict[str, Any]]
    """
    return [
        {
            "job_id": job.id,
            "state": job.state.value,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": (
                error_envelope(
                    job.error,
                    session_id=session.session_id,
                    job_id=job.id,
                )
                if job.error is not None
                else None
            ),
        }
        for job in session.queue.all_jobs()
    ]


def write_bundle(session: Session, dest: Path) -> dict[str, Any]:
    """Write the diagnostics bundle for *session* to *dest*.

    Written to disk rather than buffered in memory: console logs are capped at
    25 MB per device by the connection layer's rotating handler.

    Console transcripts are deliberately not redacted -- a credential echoed by
    a login prompt cannot be reliably scrubbed. ``manifest.json`` records
    exactly which members were processed.

    :param session: session to capture
    :type session: Session
    :param dest: path of the tar.gz to write
    :type dest: Path
    :return: the manifest that was embedded in the archive
    :rtype: dict[str, Any]
    """
    console_dir = Path(session.options.save_console_logs or "")
    has_console = bool(session.options.save_console_logs) and console_dir.is_dir()
    agent_log = console_dir.parent / "agent.log" if has_console else None
    has_agent_log = agent_log is not None and agent_log.is_file()

    absent = [
        name
        for name, present in (
            ("console-logs", has_console),
            ("agent.log", has_agent_log),
        )
        if not present
    ]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "session_id": session.session_id,
        "board_name": session.options.board_name,
        "agent_version": __version__,
        "created_at": session.created_at,
        "captured_at": time.time(),
        "state": session.state.value,
        "redacted": list(_REDACTED_MEMBERS),
        "absent": absent,
    }

    events, _ = session.buffer.read(cursor=0, limit=1_000_000)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as archive:
        _add_text(archive, "manifest.json", json.dumps(manifest, indent=2))
        _add_text(
            archive,
            "session.json",
            json.dumps(redact(session.status()), indent=2),
        )
        _add_text(
            archive,
            "config.json",
            json.dumps(redact(session.payload), indent=2),
        )
        _add_text(archive, "jobs.json", json.dumps(_jobs_payload(session), indent=2))
        _add_text(
            archive,
            "events.jsonl",
            "\n".join(json.dumps(event.__dict__) for event in events),
        )
        _add_text(archive, "threads.txt", format_threads(thread_snapshot()))
        if has_agent_log and agent_log is not None:
            archive.add(agent_log, arcname="agent.log")
        if has_console:
            archive.add(console_dir, arcname="console-logs")
    return manifest
