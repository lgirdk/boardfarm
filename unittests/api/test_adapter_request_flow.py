"""Request-level tests proving the seam's core guarantees through the agent app.

Unlike ``test_generator_adapter.py`` (which asserts on route-generation-time
artifacts: request models, skip lists, signatures) these tests drive real
HTTP requests through a FastAPI app whose routes were built by
``generate_template_routers`` with a custom adapter, and a real ``Session``
whose runtime is a lightweight fake. ``test_routers_lan.py``'s full-app
fixture (``app_module.create_app`` + ``build_session`` monkeypatch) is the
proven harness for the *default* adapter; a custom adapter is not reachable
through that path (the default adapter is baked into the template-mount list
``create_app`` builds), so these tests instead build a bare ``FastAPI()``,
include the router(s) ``generate_template_routers`` returns for a test-only
adapter, and set ``app.state.session`` directly -- exactly what the
generated handlers read (``request.app.state.session``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from boardfarm3.api.routers._generator import generate_template_routers
from boardfarm3.api.routers.adapter import DefaultAdapter, Outcome, Unsupported
from boardfarm3.api.runtime import RuntimeOptions
from boardfarm3.api.session import Session

if TYPE_CHECKING:
    from collections.abc import Iterator

HTTP_OK = 200


# ---------------------------------------------------------------------------
# Template ABC used only by these tests
# ---------------------------------------------------------------------------


class _Widget(ABC):
    """Minimal template ABC with a single required-string-param method."""

    @abstractmethod
    def poke(self, label: str) -> str:
        """Poke the widget.

        :param label: what to poke
        :type label: str
        :return: a message
        :rtype: str
        """


# ---------------------------------------------------------------------------
# Fake devices
# ---------------------------------------------------------------------------


class _EchoDevice:
    """Returns a message derived from *label*."""

    def poke(self, label: str) -> str:
        """Echo *label* back in a fixed format.

        :param label: input label
        :type label: str
        :return: formatted echo
        :rtype: str
        """
        return f"poked:{label}"


class _RaisingDevice:
    """Always raises, to exercise error containment."""

    def poke(self, label: str) -> str:
        """Raise unconditionally.

        :param label: included in the error message
        :type label: str
        :raises RuntimeError: always
        :return: never returns
        :rtype: str
        """
        msg = f"boom:{label}"
        raise RuntimeError(msg)


class _RecordingDevice:
    """Records the kwargs each call to ``poke`` actually received."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.calls: list[dict[str, Any]] = []

    def poke(self, label: str) -> str:
        """Record the call and echo *label* back.

        :param label: input label
        :type label: str
        :return: formatted echo
        :rtype: str
        """
        self.calls.append({"label": label})
        return f"poked:{label}"


# ---------------------------------------------------------------------------
# Fake device manager / runtime / harness
# ---------------------------------------------------------------------------


class _FakeDeviceManager:
    """Returns one fixed device for any queried type."""

    def __init__(self, device: object) -> None:
        """Store the device to hand back.

        :param device: the device instance every lookup returns
        :type device: object
        """
        self._device = device

    def get_devices_by_type(self, device_type: type) -> dict[str, Any]:  # noqa: ARG002
        """Return the one fake device, keyed arbitrarily.

        :param device_type: ignored
        :type device_type: type
        :return: one fake device
        :rtype: dict[str, Any]
        """
        return {"widget": self._device}


class _FakeRuntime:
    """RuntimeContext stand-in exposing only ``device_manager``."""

    def __init__(self, device_manager: object) -> None:
        """Install the given device manager.

        :param device_manager: device manager the runtime exposes
        :type device_manager: object
        """
        self.device_manager = device_manager


@contextmanager
def _build_client(adapter: DefaultAdapter, device: object) -> Iterator[TestClient]:
    """Build a bare app with one adapter-generated router and a live Session.

    The real :class:`Session` installs a global ``logging`` handler
    (``ConsoleCapture``) on construction; the full-app fixtures in
    ``test_routers_lan.py`` uninstall it via ``Session.release()`` at
    ``TestClient`` lifespan shutdown. This harness has no lifespan, so it
    uninstalls the capture handler and shuts the execution queue's worker
    thread down directly on exit, instead of calling the full
    ``Session.release()`` (which would call ``self.runtime.release()`` --
    a method the fake runtime does not implement).

    :param adapter: the response adapter under test
    :type adapter: DefaultAdapter
    :param device: fake device returned for every ``_Widget`` lookup
    :type device: object
    :yield: a TestClient wrapping the bare app
    :rtype: Iterator[TestClient]
    """
    routers, _ = generate_template_routers([_Widget], adapter=adapter)
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    session = Session(
        "s-test",
        RuntimeOptions(board_name="board-1"),
        runtime=_FakeRuntime(_FakeDeviceManager(device)),
    )
    app.state.session = session
    try:
        yield TestClient(app)
    finally:
        session.capture.uninstall()
        session.queue.shutdown()


# ---------------------------------------------------------------------------
# 2a. Success body: a custom adapter's flat-dict respond() reaches the caller
# ---------------------------------------------------------------------------


class _FlatBodyAdapter(DefaultAdapter):
    """Wraps a successful outcome in a custom flat body."""

    def respond(self, outcome: Outcome) -> Any:
        """Re-raise on failure, else return a custom flat body.

        :param outcome: dispatch outcome
        :type outcome: Outcome
        :return: a plain dict on success
        :rtype: Any
        """
        if outcome.error is not None:
            raise outcome.error
        return {"status": "ok", "payload": outcome.value}


def test_success_body_from_custom_adapter_reaches_the_caller() -> None:
    """A custom adapter's flat success body is what the HTTP caller sees."""
    with _build_client(_FlatBodyAdapter(), _EchoDevice()) as client:
        resp = client.post("/templates/_widget/poke", json={"label": "x"})
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"status": "ok", "payload": "poked:x"}


# ---------------------------------------------------------------------------
# 2b. Exception containment: an absorbing adapter turns a raise into a 200
# ---------------------------------------------------------------------------


class _AbsorbingAdapter(DefaultAdapter):
    """Converts every failure into a 200 body instead of propagating it."""

    def respond(self, outcome: Outcome) -> Any:
        """Return a flat ok/why body instead of raising.

        :param outcome: dispatch outcome
        :type outcome: Outcome
        :return: a plain dict, never a raise
        :rtype: Any
        """
        if outcome.error is not None:
            return {"ok": False, "why": str(outcome.error)}
        return {"ok": True, "value": outcome.value}


def test_absorbing_adapter_contains_the_exception_as_http_200() -> None:
    """A device method raising RuntimeError must not surface as 5xx.

    The generator's handler always builds an Outcome and hands it to
    ``adapter.respond`` -- it never re-raises on the caller's behalf. Only
    ``DefaultAdapter.respond`` chooses to re-raise; an adapter that opts out
    (like this one) fully absorbs the failure.
    """
    with _build_client(_AbsorbingAdapter(), _RaisingDevice()) as client:
        resp = client.post("/templates/_widget/poke", json={"label": "x"})
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"ok": False, "why": "boom:x"}


# ---------------------------------------------------------------------------
# 2c. check_request short-circuit
# ---------------------------------------------------------------------------


class _OptionalFieldsAdapter(DefaultAdapter):
    """Makes every field Optional, then enforces "required" itself."""

    def field_spec_for(
        self,
        name: str,  # noqa: ARG002
        annotation: Any,
        default: Any,  # noqa: ARG002
    ) -> tuple[Any, Any] | Unsupported:
        """Make every field Optional with a None default.

        :param name: parameter name (unused)
        :type name: str
        :param annotation: the parameter's Python type annotation
        :type annotation: Any
        :param default: the parameter's default (unused; always None here)
        :type default: Any
        :return: an Optional field spec
        :rtype: tuple[Any, Any] | Unsupported
        """
        return (annotation | None, None)

    def check_request(
        self,
        body: Any,
        required: frozenset[str],
    ) -> Any | None:
        """Short-circuit with a sentinel body when a required field is None.

        :param body: the parsed request model instance
        :type body: Any
        :param required: names of parameters that had no default originally
        :type required: frozenset[str]
        :return: a sentinel response, or None to proceed
        :rtype: Any | None
        """
        for name in required:
            if getattr(body, name, None) is None:
                return {"error": "missing", "field": name}
        return None


def test_check_request_short_circuits_when_a_required_field_is_missing() -> None:
    """Omitting a field the adapter made Optional hits check_request, not the device."""
    device = _RecordingDevice()
    with _build_client(_OptionalFieldsAdapter(), device) as client:
        resp = client.post("/templates/_widget/poke", json={})
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"error": "missing", "field": "label"}
    assert device.calls == []


# ---------------------------------------------------------------------------
# 2d. extra_fields reach the handler but not the target
# ---------------------------------------------------------------------------


class _TraceAdapter(DefaultAdapter):
    """Injects a trace_id field that the target method never declared."""

    def extra_fields(self) -> dict[str, tuple[Any, Any]]:
        """Add one optional trace_id field.

        :return: the extra field mapping
        :rtype: dict[str, tuple[Any, Any]]
        """
        return {"trace_id": (str | None, None)}


def test_extra_fields_reach_the_handler_but_not_the_target() -> None:
    """trace_id must validate on the request but never be forwarded to poke()."""
    device = _RecordingDevice()
    with _build_client(_TraceAdapter(), device) as client:
        resp = client.post(
            "/templates/_widget/poke",
            json={"label": "x", "trace_id": "abc-123"},
        )
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"result": "poked:x"}
    # The recording device's poke() only accepts `label`; if trace_id had
    # leaked through it would have raised TypeError instead of recording.
    assert device.calls == [{"label": "x"}]


# ---------------------------------------------------------------------------
# 2e. supports_async=False removes `mode` from the OpenAPI schema
# ---------------------------------------------------------------------------


class _SyncOnlyAdapter(DefaultAdapter):
    """Adapter that disables async dispatch."""

    supports_async = False


def test_supports_async_false_has_no_mode_parameter_in_the_openapi_schema() -> None:
    """The generated route's OpenAPI operation must not list `mode`."""
    routers, _ = generate_template_routers([_Widget], adapter=_SyncOnlyAdapter())
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    schema = app.openapi()
    operation = schema["paths"]["/templates/_widget/poke"]["post"]
    param_names = {p["name"] for p in operation.get("parameters", [])}
    assert "mode" not in param_names


# ---------------------------------------------------------------------------
# 2f. Unsupported -> SkippedMethod formats into the diagnostics endpoint shape
# ---------------------------------------------------------------------------


class _RejectAllAdapter(DefaultAdapter):
    """Rejects every parameter, forcing every method to be skipped."""

    def field_spec_for(
        self,
        name: str,  # noqa: ARG002
        annotation: Any,  # noqa: ARG002
        default: Any,  # noqa: ARG002
    ) -> tuple[Any, Any] | Unsupported:
        """Reject unconditionally.

        :param name: parameter name (unused)
        :type name: str
        :param annotation: parameter annotation (unused)
        :type annotation: Any
        :param default: parameter default (unused)
        :type default: Any
        :return: always Unsupported
        :rtype: tuple[Any, Any] | Unsupported
        """
        return Unsupported("rejected for test")


def test_skipped_method_formats_into_the_diagnostics_endpoint_shape() -> None:
    """A SkippedMethod must format into the exact dict app.py's endpoint uses.

    ``GET /diagnostics/skipped-routes`` is only reachable end-to-end through
    entrypoint-based plugin discovery (``load_plugin_routers``), which this
    test-only adapter never goes through. Instead this proves the record
    itself is endpoint-compatible: the same dict comprehension
    ``boardfarm3/api/app.py`` uses to build ``app.state.skipped_routes``
    applied to a SkippedMethod produced by an unsupported-adapter run.
    """
    _, skipped = generate_template_routers([_Widget], adapter=_RejectAllAdapter())
    assert any(s.method == "poke" for s in skipped)
    formatted = [
        {"template": s.template, "method": s.method, "reason": s.reason}
        for s in skipped
    ]
    assert {
        "template": "_Widget",
        "method": "poke",
        "reason": "rejected for test",
    } in formatted
