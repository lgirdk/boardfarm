"""Integration tests for auto-generated use-case and CPE routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.session import Session
from boardfarm3.exceptions import DeviceNotFound
from boardfarm3.templates.cpe import CPE, CPEHW, CPESW

if TYPE_CHECKING:
    from boardfarm3.api.runtime import RuntimeOptions

HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_CONFLICT = 409


class _RealCPE(CPE):
    """A concrete CPE subclass so the handler's isinstance guard passes.

    The CPE ABC only requires the ``config``/``hw``/``sw`` properties; the
    use-case under test (``get_cpu_usage``) calls ``board.get_cpu_usage()``,
    which the real function delegates to ``board.sw``. To keep the test
    self-contained we stub ``get_cpu_usage`` directly on the device — the
    route dispatches to ``fn(board=<device>)`` where ``fn`` is the use-case,
    so we monkeypatch the use-case in the fixture instead (see below).
    """

    @property
    def config(self) -> dict:
        """Return an empty config.

        :return: empty dict
        :rtype: dict
        """
        return {}

    @property
    def hw(self) -> CPEHW:
        """Return a placeholder hardware object.

        :return: None placeholder
        :rtype: CPEHW
        """
        return None  # type: ignore[return-value]

    @property
    def sw(self) -> CPESW:
        """Return a placeholder software object.

        :return: None placeholder
        :rtype: CPESW
        """
        return None  # type: ignore[return-value]


class _NotACPE:
    """A device that is NOT a CPE subclass — exercises the 422 guard."""


class _FakeDeviceManager:
    """Resolves fake devices by name and by type."""

    def __init__(self) -> None:
        """Register a real CPE (``board``) and a non-CPE (``other``)."""
        self._devices: dict[str, Any] = {"board": _RealCPE(), "other": _NotACPE()}

    def get_device_by_name(self, device_name: str) -> Any:
        """Return the fake device by name.

        :param device_name: registered name
        :type device_name: str
        :raises DeviceNotFound: when unknown
        :return: the device
        :rtype: Any
        """
        if device_name not in self._devices:
            msg = f"no device named {device_name}"
            raise DeviceNotFound(msg)
        return self._devices[device_name]

    def get_devices_by_type(self, device_type: type) -> dict[str, Any]:
        """Return devices matching the requested type.

        :param device_type: template type to filter by
        :type device_type: type
        :return: name -> device
        :rtype: dict[str, Any]
        """
        return {
            name: dev
            for name, dev in self._devices.items()
            if isinstance(dev, device_type)
        }


class _FakeRuntime:
    """RuntimeContext stand-in installing the fake device manager on boot."""

    def __init__(self) -> None:
        """Initialise unconfigured."""
        self.config: object = None
        self.device_manager: object = None

    def refresh_cmdline_args(self) -> None:
        """No-op."""

    def resolve(self, payload: dict[str, Any]) -> object:  # noqa: ARG002
        """Set a placeholder config.

        :param payload: ignored
        :type payload: dict[str, Any]
        :return: config
        :rtype: object
        """
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Install the fake device manager.

        :return: the device manager
        :rtype: object
        """
        self.device_manager = _FakeDeviceManager()
        return self.device_manager

    def boot_blocking(self) -> None:
        """No-op boot."""

    def release(self, deployment_status: dict[str, Any]) -> None:
        """No-op release.

        :param deployment_status: ignored
        :type deployment_status: dict[str, Any]
        """


@pytest.fixture(name="client")
def client_fixture(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a booted client with a real CPE (``board``) and a non-CPE (``other``).

    The ``cpe.get_cpu_usage`` use-case is monkeypatched to a trivial stub so
    the route's dispatch (``fn(board=<device>)``) returns a fixed value
    without touching real device internals.

    :param monkeypatch: pytest monkeypatch
    :type monkeypatch: pytest.MonkeyPatch
    :yield: booted test client
    :rtype: TestClient
    """
    from boardfarm3.use_cases import cpe as uc_cpe

    def _stub_get_cpu_usage(board: CPE) -> float:  # noqa: ARG001
        return 12.5

    # generate_usecase_routers() skips any function whose __module__ doesn't
    # match the module it is scanning (that check exists to filter out
    # re-exported imports). Since this stub is defined in the test module,
    # its __module__ must be rewritten to "boardfarm3.use_cases.cpe" or the
    # generator silently drops the route instead of building it.
    _stub_get_cpu_usage.__module__ = uc_cpe.__name__
    monkeypatch.setattr(uc_cpe, "get_cpu_usage", _stub_get_cpu_usage)

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=_FakeRuntime())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    with TestClient(application) as client:
        client.post(
            "/session/config",
            json={"payload": {"inventory": {}, "env": {}}, "options": {}},
        )
        client.post("/session/boot")
        yield client


def test_usecase_route_by_name_sync(client: TestClient) -> None:
    """get_cpu_usage resolves the CPE by name and returns its value.

    :param client: booted test client
    :type client: TestClient
    """
    resp = client.post("/core/use_cases/cpe/get_cpu_usage", json={"board": "board"})
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"result": 12.5}


def test_usecase_route_async_returns_202(client: TestClient) -> None:
    """Async use-case call returns 202 with a job_id.

    :param client: booted test client
    :type client: TestClient
    """
    resp = client.post(
        "/core/use_cases/cpe/get_cpu_usage?mode=async", json={"board": "board"}
    )
    assert resp.status_code == HTTP_ACCEPTED
    assert resp.json()["job_id"].startswith("j-")


def test_usecase_unknown_device_name_404(client: TestClient) -> None:
    """Unknown device name yields 404.

    :param client: booted test client
    :type client: TestClient
    """
    resp = client.post("/core/use_cases/cpe/get_cpu_usage", json={"board": "ghost"})
    assert resp.status_code == HTTP_NOT_FOUND


def test_usecase_wrong_type_device_422(client: TestClient) -> None:
    """A device that is not a CPE yields 422.

    ``get_cpu_usage`` expects a CPE; ``other`` resolves to ``_NotACPE`` which
    is not a CPE subclass, so the isinstance guard rejects it.

    :param client: booted test client
    :type client: TestClient
    """
    resp = client.post("/core/use_cases/cpe/get_cpu_usage", json={"board": "other"})
    assert resp.status_code == HTTP_UNPROCESSABLE


def test_cpe_flatten_route_present_in_schema(client: TestClient) -> None:
    """CPE sw+hw methods are flattened under /core/templates/cpe/.

    :param client: booted test client
    :type client: TestClient
    """
    schema = client.get("/openapi.json").json()
    paths = list(schema["paths"].keys())
    assert "/core/templates/cpe/reset" in paths  # from CPESW
    assert "/core/templates/cpe/power_cycle" in paths  # from CPEHW


def test_usecase_routes_present_in_schema(client: TestClient) -> None:
    """Use-case routes are mounted under /core/use_cases/.

    :param client: booted test client
    :type client: TestClient
    """
    schema = client.get("/openapi.json").json()
    assert any(p.startswith("/core/use_cases/") for p in schema["paths"])
