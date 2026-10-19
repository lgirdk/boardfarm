"""The agent's HTTP surface for sessions in a non-interactive mode."""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
import time
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.logs import artifact_dir
from boardfarm3.api.session import Session

from ._fake_mode import FakeMode
from .conftest import FakeRuntime

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from boardfarm3.api.runtime import RuntimeOptions

_FAKE = {"payload": {"inventory": {}}, "mode": "fake", "run": {}}


class _FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    FakeMode.instances.clear()


def _build(session_id: str, options: RuntimeOptions) -> Session:
    return Session(session_id, options, runtime=FakeRuntime(), modes={"fake": FakeMode})


@pytest.fixture(name="client")
def client_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(app_module, "build_session", _build)
    with TestClient(app_module.create_app("s-test", "board-1")) as test_client:
        yield test_client


def test_health_lists_the_modes(client: TestClient) -> None:
    assert client.get("/health").json()["modes"] == ["interact", "fake"]


def test_config_in_a_mode_starts_the_run(client: TestClient) -> None:
    response = client.post("/session/config", json=_FAKE)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "running"
    assert body["mode"] == "fake"
    assert body["run"] == {"state": "running", "fake": True}


def test_a_bad_run_is_a_400_and_the_session_stays_created(client: TestClient) -> None:
    response = client.post("/session/config", json={**_FAKE, "run": {"bad": True}})
    assert response.status_code == 400
    assert response.json()["error"] == "ModeRequestError"
    assert client.get("/session").json()["state"] == "created"


def test_an_unknown_mode_is_a_400(client: TestClient) -> None:
    response = client.post("/session/config", json={**_FAKE, "mode": "robot"})
    assert response.status_code == 400
    assert "unknown mode" in response.json()["message"]


def test_a_mode_session_cannot_boot(client: TestClient) -> None:
    client.post("/session/config", json=_FAKE)
    assert client.post("/session/boot").status_code == 409


def test_run_routes_answer_404_without_a_run(client: TestClient) -> None:
    assert client.get("/run").status_code == 404
    assert client.post("/run/cancel").status_code == 404
    assert client.get("/run/artifacts").status_code == 404


def test_run_reports_the_mode_status(client: TestClient) -> None:
    client.post("/session/config", json=_FAKE)
    assert client.get("/run").json() == {"state": "running", "fake": True}


def test_cancel_is_accepted_once_and_then_refused(client: TestClient) -> None:
    client.post("/session/config", json=_FAKE)
    response = client.post("/run/cancel")
    assert response.status_code == 202
    assert response.json() == {"status": "cancelling"}
    deadline = time.monotonic() + 5
    while FakeMode.instances[-1].cancel_calls == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert FakeMode.instances[-1].cancel_calls == 1
    assert client.post("/run/cancel").status_code == 409


def test_artifacts_are_the_run_directory(client: TestClient) -> None:
    client.post("/session/config", json=_FAKE)
    run_dir = artifact_dir("s-test") / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "junit.xml").write_text("<testsuites/>", encoding="utf-8")
    response = client.get("/run/artifacts")
    assert response.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        assert archive.getnames() == ["run/junit.xml"]


def test_device_calls_are_refused_in_a_mode_session(client: TestClient) -> None:
    client.post("/session/config", json=_FAKE)
    response = client.post("/devices/board/exec", json={"command": "true"})
    assert response.status_code == 409
    assert "owned by the fake run" in response.json()["detail"]


def test_the_bundle_carries_the_run_directory_and_the_mode(client: TestClient) -> None:
    client.post("/session/config", json=_FAKE)
    run_dir = artifact_dir("s-test") / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "pytest.log").write_text("1 passed\n", encoding="utf-8")
    response = client.get("/diagnostics/bundle")
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        assert "run/pytest.log" in archive.getnames()
        manifest = archive.extractfile("manifest.json")
        assert manifest is not None
        assert json.load(manifest)["mode"] == "fake"


async def test_the_console_stream_filters_by_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "build_session", _build)
    application = app_module.create_app("s-test", "board-1")
    async with application.router.lifespan_context(application):
        buffer = application.state.session.buffer
        buffer.append(
            stream="framework", device=None, job_id=None, line="framework line"
        )
        buffer.append(stream="fake", device=None, job_id=None, line="run line")
        route = next(
            candidate
            for candidate in application.routes
            if getattr(candidate, "path", None) == "/console/stream"
        )
        response = await route.endpoint(
            request=_FakeRequest(), device=None, cursor=0, stream="fake"
        )
        first = await response.body_iterator.__anext__()
        assert json.loads(first.removeprefix("data: ").strip())["line"] == "run line"
        await response.body_iterator.aclose()


async def test_the_console_stream_filters_live_events_by_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "build_session", _build)
    application = app_module.create_app("s-test", "board-1")
    async with application.router.lifespan_context(application):
        buffer = application.state.session.buffer
        route = next(
            candidate
            for candidate in application.routes
            if getattr(candidate, "path", None) == "/console/stream"
        )
        response = await route.endpoint(
            request=_FakeRequest(), device=None, cursor=0, stream="fake"
        )
        driver = asyncio.ensure_future(response.body_iterator.__anext__())
        await asyncio.sleep(0.05)
        # Subscribed before anything is appended, so both lines arrive live.
        assert len(buffer._subscribers) == 1
        buffer.append(
            stream="framework", device=None, job_id=None, line="framework line"
        )
        buffer.append(stream="fake", device=None, job_id=None, line="run line")
        first = await asyncio.wait_for(driver, timeout=5)
        assert json.loads(first.removeprefix("data: ").strip())["line"] == "run line"
        await response.body_iterator.aclose()
