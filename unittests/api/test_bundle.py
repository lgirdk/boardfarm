"""Diagnostics bundle assembly."""

from __future__ import annotations

import json
import tarfile
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.bundle import write_bundle
from boardfarm3.api.redact import REDACTED

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from boardfarm3.api.session import Session

HTTP_OK = 200
_EXPECTED = {
    "manifest.json",
    "session.json",
    "config.json",
    "jobs.json",
    "events.jsonl",
    "threads.txt",
    "agent.log",
}


@pytest.fixture(name="bundle_session")
def bundle_session_fixture(
    make_session: Callable[..., Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Session:
    """Return a session whose console logs and agent.log land under *tmp_path*.

    ``agent.log`` is installed at process start (``boardfarm3.api.__main__``),
    independently of any device connecting, so it is pre-created here rather
    than produced by the session itself -- these fixtures never boot a real
    device.

    :param make_session: session factory fixture from conftest (Task 9)
    :type make_session: Callable[..., Session]
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :return: session under test
    :rtype: Session
    """
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    session_dir = tmp_path / "s-test"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "agent.log").write_text("agent log contents\n")
    return make_session(save_console_logs=str(session_dir / "console"))


@pytest.mark.asyncio
async def test_bundle_contains_every_documented_member(
    bundle_session: Session,
    tmp_path: Path,
) -> None:
    """Every member the spec lists must be present.

    :param bundle_session: session under test
    :type bundle_session: Session
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    """
    await bundle_session.configure({"inventory": {}, "env": {}})
    dest = tmp_path / "bundle.tar.gz"
    manifest = write_bundle(bundle_session, dest)

    with tarfile.open(dest, "r:gz") as archive:
        names = set(archive.getnames())
    assert _EXPECTED.issubset(names)
    assert manifest["session_id"] == "s-test"
    assert manifest["board_name"] == "board"
    assert manifest["redacted"] == ["session.json", "config.json"]


@pytest.mark.asyncio
async def test_bundle_redacts_credentials_in_config(
    bundle_session: Session,
    tmp_path: Path,
) -> None:
    """A password in the payload must not survive into the bundle.

    :param bundle_session: session under test
    :type bundle_session: Session
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    """
    await bundle_session.configure(
        {"inventory": {"board": {"password": "hunter2"}}, "env": {}},
    )
    dest = tmp_path / "bundle.tar.gz"
    write_bundle(bundle_session, dest)

    with tarfile.open(dest, "r:gz") as archive:
        member = archive.extractfile("config.json")
        assert member is not None
        config = json.loads(member.read())
    assert config["inventory"]["board"]["password"] == REDACTED


@pytest.mark.asyncio
async def test_bundle_records_absent_members(
    bundle_session: Session,
    tmp_path: Path,
) -> None:
    """A missing console-log directory must be reported, not crash the bundle.

    :param bundle_session: session under test
    :type bundle_session: Session
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    """
    await bundle_session.configure({"inventory": {}, "env": {}})
    dest = tmp_path / "bundle.tar.gz"
    manifest = write_bundle(bundle_session, dest)
    assert "console-logs" in manifest["absent"]


@pytest.mark.asyncio
async def test_bundle_jobs_carry_tracebacks(
    bundle_session: Session,
    tmp_path: Path,
) -> None:
    """jobs.json is where a failed run's traceback has to land.

    :param bundle_session: session under test
    :type bundle_session: Session
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    """
    await bundle_session.configure({"inventory": {}, "env": {}})

    def boom() -> None:
        msg = "kaboom"
        raise ValueError(msg)

    # submit(mode="sync") re-raises the job's exception to the caller.
    with pytest.raises(ValueError, match="kaboom"):
        await bundle_session.queue.submit(boom, mode="sync")

    dest = tmp_path / "bundle.tar.gz"
    write_bundle(bundle_session, dest)

    with tarfile.open(dest, "r:gz") as archive:
        member = archive.extractfile("jobs.json")
        assert member is not None
        jobs = json.loads(member.read())
    failed = [job for job in jobs if job["state"] == "error"]
    assert failed
    assert "ValueError: kaboom" in "".join(failed[0]["error"]["traceback"])


def test_bundle_includes_agent_log_for_a_created_session_with_no_console_dir(
    make_session: Callable[..., Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent.log must survive a crash before any device ever connects.

    Before the fix, agent.log's inclusion was gated on console/ existing,
    but console/ is only created lazily on the first device connect while
    agent.log is installed at process start. A session that fails in the
    ``created`` state -- before ``configure()`` is even called, let alone a
    device connection -- has an agent.log on disk but console/ genuinely
    does not exist, and the bundle used to silently drop agent.log too.

    :param make_session: session factory fixture from conftest (Task 9)
    :type make_session: Callable[..., Session]
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    session_dir = tmp_path / "s-test"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "agent.log").write_text("crash before boot\n")

    session = make_session()
    assert not (session_dir / "console").exists()

    dest = tmp_path / "bundle.tar.gz"
    manifest = write_bundle(session, dest)

    with tarfile.open(dest, "r:gz") as archive:
        names = set(archive.getnames())
    assert "agent.log" in names
    assert "console-logs" in manifest["absent"]
    assert "agent.log" not in manifest["absent"]


def test_bundle_route_streams_gzip() -> None:
    """The HTTP surface must return a real gzip stream."""
    app = app_module.create_app("s-test", "board")
    with TestClient(app) as client:
        response = client.get("/diagnostics/bundle")
    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "application/gzip"
    assert response.content[:2] == b"\x1f\x8b"
