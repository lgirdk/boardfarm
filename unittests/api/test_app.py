"""Unit tests for the boardfarm runtime agent HTTP surface."""

from __future__ import annotations

import asyncio
import io
import logging
import tarfile
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.session import Session, SessionState
from boardfarm3.exceptions import EnvConfigError

if TYPE_CHECKING:
    from pathlib import Path

    from boardfarm3.api.runtime import RuntimeOptions

HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422


class FakeRuntime:
    """RuntimeContext stand-in for HTTP-level tests."""

    def __init__(self, *, resolve_error: Exception | None = None) -> None:
        """Initialise the fake.

        :param resolve_error: raise this from resolve()
        :type resolve_error: Exception | None
        """
        self.resolve_error = resolve_error
        self.config = None
        self.device_manager = None
        self.devices: dict[str, Any] = {}

    def refresh_cmdline_args(self) -> None:
        """Re-materialise options. No-op for the fake."""

    def resolve(self, payload: dict[str, Any]) -> object:  # noqa: ARG002
        """Resolve the payload.

        The configured error is an exception instance, so darglint2 cannot
        infer its type from ``raise self.resolve_error``.

        # noqa: DAR401
        # noqa: DAR402

        :param payload: opaque payload
        :type payload: dict[str, Any]
        :raises Exception: when configured to fail
        :return: placeholder config
        :rtype: object
        """
        if self.resolve_error:
            raise self.resolve_error
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Register devices.

        :return: placeholder device manager
        :rtype: object
        """
        self.device_manager = object()
        return self.device_manager

    def boot_blocking(self) -> None:
        """Boot successfully."""

    def release(self, deployment_status: dict[str, Any]) -> None:
        """Release devices.

        :param deployment_status: deployment outcome
        :type deployment_status: dict[str, Any]
        """


class _AbstractRadio(ABC):
    """A minimal Template stand-in, independent of the real templates package."""

    @abstractmethod
    def toggle(self) -> None:
        """Toggle the radio."""


class _ConcreteRadio(_AbstractRadio):
    """A concrete device satisfying ``_AbstractRadio``."""

    def toggle(self) -> None:
        """Toggle the radio."""


class _FakeDeviceManager:
    """Returns one fixed device regardless of the requested type."""

    def get_devices_by_type(self, device_type: type) -> dict[str, object]:
        """Return the fixed device, ignoring the requested type.

        :param device_type: the type the caller filters by; unused, the fake
            always returns the same fixed device
        :type device_type: type
        :return: one fake device keyed by name
        :rtype: dict[str, object]
        """
        del device_type
        return {"router": _ConcreteRadio()}


@pytest.fixture(name="client")
def client_fixture(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a test client whose session uses a fake runtime.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :yield: test client
    :rtype: TestClient
    """

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=FakeRuntime())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    with TestClient(application) as test_client:
        yield test_client


def test_health_is_available_before_configure(client: TestClient) -> None:
    """Health must answer while the session is still unconfigured.

    :param client: test client
    :type client: TestClient
    """
    response = client.get("/health")
    assert response.status_code == HTTP_OK
    assert response.json()["state"] == SessionState.CREATED.value


def test_config_then_boot_reaches_ready(client: TestClient) -> None:
    """Configuring then booting drives the session to ready.

    :param client: test client
    :type client: TestClient
    """
    assert (
        client.post(
            "/session/config",
            json={"payload": {"inventory": {}, "env": {}}},
        ).status_code
        == HTTP_OK
    )
    assert client.post("/session/boot").status_code == HTTP_ACCEPTED
    assert client.get("/session").json()["state"] == SessionState.READY.value


def test_bad_payload_returns_400_with_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A payload the resolve hook rejects fails fast with the error envelope.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    """

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(
            session_id,
            options,
            runtime=FakeRuntime(resolve_error=EnvConfigError("bad inventory")),
        )

    monkeypatch.setattr(app_module, "build_session", build)
    with TestClient(app_module.create_app("s-test", "board-1")) as client:
        response = client.post(
            "/session/config",
            json={"payload": {"inventory": {}, "env": {}}},
        )
        assert response.status_code == HTTP_BAD_REQUEST
        body = response.json()
        assert body["error"] == "EnvConfigError"
        assert body["message"] == "bad inventory"
        assert body["session_id"] == "s-test"


def test_boot_before_config_returns_409(client: TestClient) -> None:
    """Booting an unconfigured session is rejected.

    :param client: test client
    :type client: TestClient
    """
    assert client.post("/session/boot").status_code == HTTP_CONFLICT


def test_console_is_cursor_paged(client: TestClient) -> None:
    """Console reads return events and a next cursor.

    :param client: test client
    :type client: TestClient
    """
    client.post("/session/config", json={"payload": {"inventory": {}, "env": {}}})
    body = client.get("/console").json()
    assert "events" in body
    assert "cursor" in body


def test_unknown_job_returns_404(client: TestClient) -> None:
    """An unknown job id is a 404.

    :param client: test client
    :type client: TestClient
    """
    assert client.get("/jobs/j-nope").status_code == HTTP_NOT_FOUND


# -- mode must be a Literal["sync", "async"] --------------------------------
#
# ExecutionQueue.submit() treats anything that is not exactly the string
# "async" as sync. An unconstrained `mode` query parameter would therefore
# let a typo like "asnyc" (or a differently-cased "ASYNC") silently run a
# real pexpect boot synchronously on the FastAPI event loop instead of being
# rejected outright.


@pytest.mark.parametrize("bad_mode", ["ASYNC", "bogus"])
def test_boot_rejects_invalid_mode_value(client: TestClient, bad_mode: str) -> None:
    """An invalid mode value 422s before the route body -- and the queue -- runs.

    Deliberately posted without configuring first: the session is still
    CREATED, so if mode validation were missing or broken this would fall
    through to the 409-conflict branch instead of 422, which would make the
    two status codes indistinguishable in this test.

    :param client: test client
    :type client: TestClient
    :param bad_mode: an invalid mode value
    :type bad_mode: str
    """
    response = client.post(f"/session/boot?mode={bad_mode}")
    assert response.status_code == HTTP_UNPROCESSABLE


def test_boot_async_mode_completes_in_background(client: TestClient) -> None:
    """mode=async returns without waiting, and the boot still finishes.

    :param client: test client
    :type client: TestClient
    """
    client.post("/session/config", json={"payload": {"inventory": {}, "env": {}}})
    response = client.post("/session/boot?mode=async")
    assert response.status_code == HTTP_ACCEPTED
    for _ in range(40):
        if client.get("/session").json()["state"] == SessionState.READY.value:
            break
        time.sleep(0.05)
    assert client.get("/session").json()["state"] == SessionState.READY.value


# -- Session.configure() silently drops unknown option keys -----------------
#
# Session.configure() applies overrides with a hasattr-guarded setattr, so an
# unknown key passed straight through would vanish with no error anywhere.
# The API layer must reject it instead.


def test_config_rejects_unknown_option_key(client: TestClient) -> None:
    """An unrecognised key in ``options`` is a visible 422, not a silent no-op.

    :param client: test client
    :type client: TestClient
    """
    response = client.post(
        "/session/config",
        json={
            "payload": {"inventory": {}, "env": {}},
            "options": {"bogus_option": True},
        },
    )
    assert response.status_code == HTTP_UNPROCESSABLE


def test_config_applies_known_option_overrides(client: TestClient) -> None:
    """A known option key reaches the session's RuntimeOptions.

    :param client: test client
    :type client: TestClient
    """
    client.post(
        "/session/config",
        json={
            "payload": {"inventory": {}, "env": {}},
            "options": {"legacy": True},
        },
    )
    assert client.app.state.session.options.legacy is True


# -- DELETE /session must tolerate a second, implicit release ---------------
#
# Session.release() submits to the execution queue and then shuts the queue
# down; the lifespan shutdown handler calls release() again on the way out
# of the `with TestClient(...)` block, so DELETE /session must not leave the
# session in a state where that second call blows up.


def test_delete_session_is_idempotent(client: TestClient) -> None:
    """Releasing an already-released session is safe, not a crash.

    :param client: test client
    :type client: TestClient
    """
    first = client.delete("/session")
    assert first.status_code == HTTP_OK
    assert first.json() == {"status": "released"}
    second = client.delete("/session")
    assert second.status_code == HTTP_OK


# -- Session.__init__ installs a global logging handler ---------------------
#
# Two ConsoleCapture instances installed at once step on each other through
# the shared pexpect/boardfarm3 loggers, so every session built by the app
# must be released -- and therefore uninstalled -- when the app shuts down,
# even if the session was never configured.


def test_client_teardown_uninstalls_console_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exiting the TestClient context uninstalls the session's console capture.

    A session that never leaves CREATED (no ``/session/config`` call, as
    here) must still be released when the app shuts down. A leaked handler
    here would corrupt ``test_console.py``'s
    ``test_uninstall_restores_logger_state`` depending on test order.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    """

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=FakeRuntime())

    monkeypatch.setattr(app_module, "build_session", build)
    with TestClient(app_module.create_app("s-test", "board-1")) as client:
        assert logging.getLogger("pexpect").propagate is False
        assert client.get("/health").status_code == HTTP_OK
    assert logging.getLogger("pexpect").propagate is True


# -- GET /devices -------------------------------------------------------


def test_devices_before_configure_is_empty(client: TestClient) -> None:
    """No device manager yet means an empty device list, not an error.

    :param client: test client
    :type client: TestClient
    """
    assert client.get("/devices").json() == {"devices": []}


def test_devices_lists_registered_devices_with_templates(client: TestClient) -> None:
    """Each device reports its name, concrete type and abstract template bases.

    :param client: test client
    :type client: TestClient
    """
    client.app.state.session.runtime.device_manager = _FakeDeviceManager()
    response = client.get("/devices")
    assert response.json() == {
        "devices": [
            {
                "name": "router",
                "type": "_ConcreteRadio",
                "templates": ["_AbstractRadio"],
            },
        ],
    }


# -- GET /jobs/{job_id} and GET /jobs/{job_id}/console -----------------------


def test_job_status_and_console_for_a_completed_job(client: TestClient) -> None:
    """A finished job reports its state and exposes its own console slice.

    :param client: test client
    :type client: TestClient
    """
    client.post("/session/config", json={"payload": {"inventory": {}, "env": {}}})
    client.post("/session/boot")
    queue = client.app.state.session.queue
    job_id = next(reversed(queue._jobs))
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["job_id"] == job_id
    assert body["state"] == "done"
    assert body["error"] is None
    console = client.get(f"/jobs/{job_id}/console")
    assert console.status_code == HTTP_OK
    assert "events" in console.json()


# -- GET /console/archive ----------------------------------------------------


def test_console_archive_404_when_not_configured(client: TestClient) -> None:
    """No save_console_logs directory means a 404, not an empty archive.

    :param client: test client
    :type client: TestClient
    """
    assert client.get("/console/archive").status_code == HTTP_NOT_FOUND


def test_console_archive_returns_tar_of_saved_logs(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """When console logs are saved to disk, the archive tars that directory.

    :param client: test client
    :type client: TestClient
    :param tmp_path: pytest temporary directory fixture
    :type tmp_path: Path
    """
    (tmp_path / "board.log").write_text("login:\n", encoding="utf-8")
    client.post(
        "/session/config",
        json={
            "payload": {"inventory": {}, "env": {}},
            "options": {"save_console_logs": str(tmp_path)},
        },
    )
    response = client.get("/console/archive")
    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "application/gzip"
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        names = archive.getnames()
    assert "console-logs/board.log" in names


# -- GET /console/stream: cleanup on disconnect ------------------------------
#
# Starlette's StreamingResponse, as served by uvicorn's HTTP protocols (which
# negotiate ASGI spec_version 2.3), races listen_for_disconnect() against
# stream_response() in a task group; whichever finishes first cancels the
# other. TestClient cannot reproduce this: its ASGI transport (starlette
# 1.6.0) drives the whole application call to completion inside a single
# blocking portal.call() before it will hand back a response, so a request
# against an endless generator such as this one hangs forever under
# TestClient -- there is no way to open it, let alone abandon it, through
# client.get()/client.stream(). This test instead drives the route's
# generator directly and cancels the task reading it, which is exactly the
# mechanism a real disconnect triggers.


@pytest.mark.asyncio
async def test_console_stream_cleans_up_subscriber_on_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling the task driving the SSE generator runs subscribe()'s finally.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    """

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=FakeRuntime())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    async with application.router.lifespan_context(application):
        route = next(
            candidate
            for candidate in application.routes
            if getattr(candidate, "path", None) == "/console/stream"
        )
        response = await route.endpoint(device=None)
        driver = asyncio.ensure_future(response.body_iterator.__anext__())
        await asyncio.sleep(0.05)
        assert len(application.state.session.buffer._subscribers) == 1
        driver.cancel()
        with pytest.raises(asyncio.CancelledError):
            await driver
        assert len(application.state.session.buffer._subscribers) == 0
