"""The agent's HTTP surface for sessions in a non-interactive mode."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import tarfile
import time
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.logs import artifact_dir
from boardfarm3.api.session import Session

from ._fake_mode import FakeMode
from .conftest import FakeRuntime

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from boardfarm3.api.runtime import RuntimeOptions

_FAKE = {"payload": {"inventory": {}}, "mode": "fake", "run": {}}
_SECRETS = ("s3cr3t-cfg", "u;s3cr3t-ldap")
_WITH_SECRETS: dict[str, Any] = {
    **_FAKE,
    "run": {"env": {"UIM_PWD": _SECRETS[0]}},
    "options": {"plugin_args": {"ldap_credentials": _SECRETS[1]}},
}


class _FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


class _FailingCancelMode(FakeMode):
    async def cancel(self) -> bool:
        self.cancel_calls += 1
        msg = "cannot signal the process group"
        raise PermissionError(msg)


class _SelfCancellingMode(FakeMode):
    """The first cancel ends its task as cancelled; later ones are normal."""

    async def cancel(self) -> bool:
        self.cancel_calls += 1
        if self.cancel_calls == 1:
            raise asyncio.CancelledError
        return False


class _CountingMode(FakeMode):
    """A run whose summary carries the test counts a pytest run reports."""

    def status(self) -> dict[str, Any]:
        return {**super().status(), "counts": {"passed": 3, "failed": 1}}


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    FakeMode.instances.clear()


def _build(session_id: str, options: RuntimeOptions) -> Session:
    return Session(session_id, options, runtime=FakeRuntime(), modes={"fake": FakeMode})


def _build_with(
    mode: type[FakeMode],
) -> Callable[[str, RuntimeOptions], Session]:
    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=FakeRuntime(), modes={"fake": mode})

    return build


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


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {**_WITH_SECRETS, "env": _WITH_SECRETS["run"]["env"]},
            id="unknown-top-level-key",
        ),
        pytest.param(
            {key: value for key, value in _WITH_SECRETS.items() if key != "payload"},
            id="no-payload",
        ),
        pytest.param(
            {**_WITH_SECRETS, "options": {"ldap_credentials": _SECRETS[1]}},
            id="unknown-option",
        ),
    ],
)
def test_validation_errors_never_echo_the_request(
    client: TestClient, body: dict[str, Any]
) -> None:
    response = client.post("/session/config", json=body)
    assert response.status_code == 422
    for secret in _SECRETS:
        assert secret not in response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail
    assert all(
        isinstance(error, dict) and {"loc", "msg"} <= error.keys() for error in detail
    )


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


def test_a_cancel_that_fails_in_the_background_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def cancel_errors() -> list[logging.LogRecord]:
        return [
            record
            for record in caplog.records
            if record.name == "boardfarm3.api.app" and record.levelno == logging.ERROR
        ]

    monkeypatch.setattr(app_module, "build_session", _build_with(_FailingCancelMode))
    with TestClient(app_module.create_app("s-test", "board-1")) as client:
        client.post("/session/config", json=_FAKE)
        with caplog.at_level(logging.ERROR, logger="boardfarm3.api.app"):
            response = client.post("/run/cancel")
            deadline = time.monotonic() + 5
            while not cancel_errors() and time.monotonic() < deadline:
                time.sleep(0.01)
    assert response.status_code == 202
    assert response.json() == {"status": "cancelling"}
    errors = cancel_errors()
    assert len(errors) == 1
    assert "s-test" in errors[0].getMessage()
    assert errors[0].exc_info is not None
    assert isinstance(errors[0].exc_info[1], PermissionError)


async def test_a_background_cancel_that_ends_cancelled_is_not_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(app_module, "build_session", _build_with(_SelfCancellingMode))
    application = app_module.create_app("s-test", "board-1")
    async with application.router.lifespan_context(application):
        await application.state.session.configure({}, {}, mode="fake", run={})
        route = next(
            candidate
            for candidate in application.routes
            if getattr(candidate, "path", None) == "/run/cancel"
        )
        with caplog.at_level(logging.ERROR):
            assert await route.endpoint() == {"status": "cancelling"}
            # Enough turns for the task to end and its done-callback to run.
            for _ in range(3):
                await asyncio.sleep(0)
        assert FakeMode.instances[-1].cancel_calls == 1
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


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


def test_the_bundle_session_json_has_the_mode_and_run_but_never_run_env(
    client: TestClient,
) -> None:
    canary = "canary-run-env-value"
    body = {**_FAKE, "run": {"env": {"UIM_PWD": canary}}}
    assert client.post("/session/config", json=body).status_code == 200
    response = client.get("/diagnostics/bundle")
    members: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        for name in ("session.json", "config.json"):
            member = archive.extractfile(name)
            assert member is not None
            members[name] = member.read().decode("utf-8")
    session_json = json.loads(members["session.json"])
    assert session_json["mode"] == "fake"
    assert session_json["run"] == {"state": "running", "fake": True}
    for name, text in members.items():
        assert canary not in text, f"{name} carries run.env"


def test_the_bundle_session_json_keeps_the_runs_pass_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "build_session", _build_with(_CountingMode))
    with TestClient(app_module.create_app("s-test", "board-1")) as client:
        assert client.post("/session/config", json=_FAKE).status_code == 200
        response = client.get("/diagnostics/bundle")
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        member = archive.extractfile("session.json")
        assert member is not None
        session_json = json.load(member)
    assert session_json["run"]["counts"] == {"passed": 3, "failed": 1}


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
