"""Integration tests: control and a real agent run pytest sessions end to end.

The agent is a real ``boardfarm3.api`` process (ProcessLauncher), and pytest
a real child of it. The suite is tiny, the board has no devices, and no
lockable-resources plugin is installed, so nothing here needs a lab.
"""

from __future__ import annotations

import asyncio
import io
import tarfile
import time
from typing import TYPE_CHECKING, Any

import pytest

from boardfarm3_control.store import DiagnosticsStore

pytest.importorskip("pytest_boardfarm3.api.mode")

if TYPE_CHECKING:
    from pathlib import Path

    import httpx

_SUITE = (
    "import time\n\nimport pytest\n\n\n"
    "def test_MVX_TST_1():\n    pass\n\n\n"
    "def test_MVX_TST_2():\n    assert False\n\n\n"
    "@pytest.fixture\ndef noisy():\n    yield\n    print('teardown ran', flush=True)\n\n\n"
    "def test_MVX_TST_3(noisy):\n    print('sleeping', flush=True)\n    time.sleep(120)\n"
)
_DEADLINE = 120.0
_REPORTS = {
    "run/junit.xml",
    "run/report.html",
    "run/pytest.log",
    "run/progress.jsonl",
    "run/run.json",
}


@pytest.fixture
def suite(tmp_path: Path) -> Path:
    """Write the tiny suite to ``<tmp>/repo/tests``.

    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    :return: the suite root
    :rtype: Path
    """
    root = tmp_path / "repo" / "tests"
    root.mkdir(parents=True)
    (root / "test_demo.py").write_text(_SUITE, encoding="utf-8")
    return root


def _request(suite: Path, run: dict[str, Any]) -> dict[str, Any]:
    return {
        "board_name": "integration-board",
        "runtime_profile": "local",
        "mode": "pytest",
        "payload": {
            "inventory": {"integration-board": {"devices": []}},
            "env": {"environment_def": {}},
        },
        "options": {"skip_boot": True},
        "run": run,
        "agent_env": {
            "BOARDFARM_PYTEST_ROOT": str(suite),
            "BOARDFARM_RUN_CANCEL_GRACE": "20",
        },
    }


async def _create(client: httpx.AsyncClient, body: dict[str, Any]) -> str:
    resp = await client.post("/sessions", json=body)
    assert resp.status_code == 202, resp.text
    created = resp.json()
    assert created["mode"] == "pytest"
    assert created["state"] == "running"
    return str(created["session_id"])


async def _finished(client: httpx.AsyncClient, sid: str) -> dict[str, Any]:
    deadline = time.monotonic() + _DEADLINE
    while True:
        resp = await client.get(f"/sessions/{sid}")
        assert resp.status_code == 200, resp.text
        body: dict[str, Any] = resp.json()
        if (body.get("run") or {}).get("state") == "finished":
            return body
        if time.monotonic() > deadline:
            msg = f"the run of {sid} did not finish: {body}"
            raise AssertionError(msg)
        await asyncio.sleep(0.5)


async def _wait_for_line(client: httpx.AsyncClient, sid: str, text: str) -> None:
    deadline = time.monotonic() + _DEADLINE
    while True:
        resp = await client.get(f"/sessions/{sid}/console", params={"stream": "pytest"})
        assert resp.status_code == 200, resp.text
        if any(text in event["line"] for event in resp.json()["events"]):
            return
        if time.monotonic() > deadline:
            msg = f"{text!r} never reached the pytest stream of {sid}"
            raise AssertionError(msg)
        await asyncio.sleep(0.5)


async def test_a_pytest_session_passes_and_serves_its_reports(
    control_client: httpx.AsyncClient,
    suite: Path,
) -> None:
    """A passing run finishes, counts its test and serves every report."""
    sid = await _create(control_client, _request(suite, {"test_names": ["MVX_TST-1"]}))
    try:
        body = await _finished(control_client, sid)
        assert body["state"] == "finished"
        assert body["run"]["outcome"] == "passed"
        assert body["run"]["counts"] == {
            "passed": 1,
            "failed": 0,
            "error": 0,
            "skipped": 0,
        }
        resp = await control_client.get(f"/sessions/{sid}/run/artifacts")
        assert resp.status_code == 200
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as archive:
            assert set(archive.getnames()) >= _REPORTS
    finally:
        await control_client.delete(f"/sessions/{sid}")


async def test_test_files_and_run_args_reach_pytest(
    control_client: httpx.AsyncClient,
    suite: Path,
) -> None:
    """A file selection with a -k filter runs exactly the two quick tests."""
    sid = await _create(
        control_client,
        _request(
            suite,
            {"test_files": ["test_demo.py"], "args": ["-k", "not MVX_TST_3"]},
        ),
    )
    try:
        body = await _finished(control_client, sid)
        assert body["run"]["outcome"] == "failed"
        assert body["run"]["exit_code"] == 1
        assert body["run"]["counts"] == {
            "passed": 1,
            "failed": 1,
            "error": 0,
            "skipped": 0,
        }
        run = (await control_client.get(f"/sessions/{sid}/run")).json()
        assert run["selection"] == {"test_files": ["test_demo.py"]}
        assert str((suite / "test_demo.py").resolve()) in run["command"]
    finally:
        await control_client.delete(f"/sessions/{sid}")


async def test_cancelling_a_pytest_session_runs_fixture_teardown(
    control_client: httpx.AsyncClient,
    suite: Path,
) -> None:
    """A cancel ends the run as cancelled, after the fixture's teardown."""
    sid = await _create(control_client, _request(suite, {"test_names": ["MVX_TST-3"]}))
    try:
        await _wait_for_line(control_client, sid, "sleeping")
        resp = await control_client.post(f"/sessions/{sid}/run/cancel")
        assert resp.status_code == 202
        assert resp.json() == {"status": "cancelling"}
        body = await _finished(control_client, sid)
        assert body["run"]["outcome"] == "cancelled"
        await _wait_for_line(control_client, sid, "teardown ran")
    finally:
        await control_client.delete(f"/sessions/{sid}")


async def test_a_name_that_matches_nothing_ends_with_no_tests(
    control_client: httpx.AsyncClient,
    suite: Path,
) -> None:
    """An unmatched name is reported, and a run that selects nothing is no_tests."""
    sid = await _create(control_client, _request(suite, {"test_names": ["NOPE-9"]}))
    try:
        body = await _finished(control_client, sid)
        assert body["run"]["outcome"] == "no_tests"
        assert body["run"]["unmatched"] == ["NOPE-9"]
    finally:
        await control_client.delete(f"/sessions/{sid}")


async def test_deleting_a_running_session_keeps_its_cancelled_result(
    control_client: httpx.AsyncClient,
    suite: Path,
) -> None:
    """DELETE cancels the run first; meta.json and the bundle keep its result."""
    sid = await _create(control_client, _request(suite, {"test_names": ["MVX_TST-3"]}))
    await _wait_for_line(control_client, sid, "sleeping")
    resp = await control_client.delete(f"/sessions/{sid}")
    assert resp.status_code == 200, resp.text
    store = DiagnosticsStore()
    meta = store.read_meta(sid)
    assert meta is not None
    assert meta["mode"] == "pytest"
    assert meta["run"]["outcome"] == "cancelled"
    with tarfile.open(store.bundle_path(sid), mode="r:gz") as bundle:
        assert any(name.endswith("run/junit.xml") for name in bundle.getnames())
