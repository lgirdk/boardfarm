"""The full gzipped console log: capture, bundle and download."""

from __future__ import annotations

import gzip
import logging
import tarfile
import zlib
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.bundle import write_bundle
from boardfarm3.api.console import ConsoleCapture, EventBuffer
from boardfarm3.api.execution import current_job_id

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from boardfarm3.api.session import Session

HTTP_OK = 200
HTTP_NOT_FOUND = 404


def _read(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return handle.read().splitlines()


def _log(message: str, job_id: str | None = None) -> None:
    token = current_job_id.set(job_id)
    try:
        logging.getLogger("boardfarm3.test").info(message)
    finally:
        current_job_id.reset(token)


@pytest.fixture(name="capture")
def capture_fixture(tmp_path: Path) -> Iterator[ConsoleCapture]:
    """Return an installed capture writing its full log under *tmp_path*.

    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    :yield: installed capture
    :rtype: Iterator[ConsoleCapture]
    """
    console_capture = ConsoleCapture(EventBuffer(), log_dir=tmp_path / "logs")
    console_capture.install()
    yield console_capture
    console_capture.uninstall()


def test_every_line_lands_in_one_file_in_arrival_order(
    capture: ConsoleCapture, tmp_path: Path
) -> None:
    _log("one", "job-1")
    _log("idle")
    capture.record(stream="pytest", device=None, job_id="run-s-1", line="two")
    _log("three", "job-2")
    capture.close_file()
    assert [path.name for path in (tmp_path / "logs").iterdir()] == [
        "console_full.txt.gz"
    ]
    assert _read(tmp_path / "logs" / "console_full.txt.gz") == [
        "one",
        "idle",
        "two",
        "three",
    ]


def test_lines_are_readable_while_the_file_is_still_open(
    capture: ConsoleCapture,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    _log("live", "job-1")
    data = (tmp_path / "logs" / "console_full.txt.gz").read_bytes()
    # No trailer yet, but every line written so far decompresses.
    assert zlib.decompressobj(31).decompress(data) == b"live\n"


def test_reopening_appends_a_member_readable_as_one_stream(
    capture: ConsoleCapture, tmp_path: Path
) -> None:
    _log("before", "job-1")
    capture.close_file()
    _log("after", "job-2")
    capture.close_file()
    assert _read(tmp_path / "logs" / "console_full.txt.gz") == ["before", "after"]


def test_multiline_values_are_written_whole(
    capture: ConsoleCapture, tmp_path: Path
) -> None:
    capture.record(stream="pytest", device=None, job_id="run-s-1", line="a\nb")
    capture.close_file()
    assert _read(tmp_path / "logs" / "console_full.txt.gz") == ["a", "b"]


def test_an_unwritable_log_dir_still_fills_the_buffer(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    buffer = EventBuffer()
    console_capture = ConsoleCapture(buffer, log_dir=blocker)
    console_capture.install()
    try:
        _log("kept")
    finally:
        console_capture.uninstall()
    assert [event.line for event in buffer.read()[0]] == ["kept"]
    assert console_capture.log_file() is None


def test_copy_log_file_gives_a_complete_stream(
    capture: ConsoleCapture, tmp_path: Path
) -> None:
    _log("one", "job-1")
    copy = tmp_path / "copy.txt.gz"
    assert capture.copy_log_file(copy)
    assert _read(copy) == ["one"]


def test_copy_log_file_without_a_log_copies_nothing(
    capture: ConsoleCapture, tmp_path: Path
) -> None:
    copy = tmp_path / "copy.txt.gz"
    assert not capture.copy_log_file(copy)
    assert not copy.exists()


def test_bundle_carries_the_full_log(
    make_session: Callable[..., Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    session = make_session()
    session.capture.record(stream="framework", device=None, job_id="j-1", line="hi")
    dest = tmp_path / "bundle.tar.gz"
    write_bundle(session, dest)
    with tarfile.open(dest, "r:gz") as archive:
        member = archive.extractfile("console_full.txt.gz")
        assert member is not None
        assert gzip.decompress(member.read()) == b"hi\n"


def _download_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    from boardfarm3.api.session import Session as RealSession
    from unittests.api.conftest import FakeRuntime

    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setattr(
        app_module,
        "build_session",
        lambda sid, options: RealSession(sid, options, runtime=FakeRuntime()),
    )
    return TestClient(
        app_module.create_app("s-test", "board-1"), raise_server_exceptions=False
    )


def test_download_serves_the_full_log_as_gzip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with _download_client(monkeypatch, tmp_path) as client:
        _log("boot", "j-1")
        _log("typed")
        response = client.get("/console/download")
    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "application/gzip"
    assert (
        'filename="s-test-console_full.txt.gz"'
        in response.headers["content-disposition"]
    )
    assert "content-encoding" not in response.headers
    assert gzip.decompress(response.content) == b"boot\ntyped\n"


def test_download_without_a_log_is_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with _download_client(monkeypatch, tmp_path) as client:
        response = client.get("/console/download")
    assert response.status_code == HTTP_NOT_FOUND
    assert response.json()["detail"]["error"] == "NoConsoleLog"
