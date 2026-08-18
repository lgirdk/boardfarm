"""Unit tests for the LAN template router."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.session import Session

if TYPE_CHECKING:
    from boardfarm3.api.runtime import RuntimeOptions

HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409


# ---------------------------------------------------------------------------
# Fake LAN device
# ---------------------------------------------------------------------------


class _FakeLAN:
    """Minimal LAN stand-in — implements only the four tested methods."""

    def ping(  # noqa: PLR0913
        self,
        ping_ip: str,  # noqa: ARG002
        ping_count: int = 4,  # noqa: ARG002
        ping_interface: str | None = None,  # noqa: ARG002
        options: str = "",  # noqa: ARG002
        timeout: int = 50,  # noqa: ARG002
        json_output: bool = False,  # noqa: ARG002
    ) -> bool:
        """Return True unconditionally.

        :return: True
        :rtype: bool
        """
        return True

    def get_interface_macaddr(self, interface: str) -> str:  # noqa: ARG002
        """Return a fixed MAC address.

        :param interface: ignored
        :type interface: str
        :return: fixed MAC
        :rtype: str
        """
        return "aa:bb:cc:dd:ee:ff"

    def get_interface_ipv4addr(self, interface: str) -> str:  # noqa: ARG002
        """Return a fixed IPv4 address.

        :param interface: ignored
        :type interface: str
        :return: fixed IPv4
        :rtype: str
        """
        return "192.168.1.100"

    def set_link_state(self, interface: str, state: str) -> None:
        """No-op.

        :param interface: ignored
        :type interface: str
        :param state: ignored
        :type state: str
        """


# ---------------------------------------------------------------------------
# Fake device manager
# ---------------------------------------------------------------------------


class _FakeLANDeviceManager:
    """Returns one _FakeLAN when queried for any type."""

    def get_devices_by_type(self, device_type: type) -> dict[str, Any]:  # noqa: ARG002
        """Return a single fake LAN device.

        :param device_type: ignored
        :type device_type: type
        :return: one fake device
        :rtype: dict[str, Any]
        """
        return {"lan": _FakeLAN()}


# ---------------------------------------------------------------------------
# Fake runtimes
# ---------------------------------------------------------------------------


class _FakeRuntimeWithLAN:
    """RuntimeContext stand-in that installs a LAN device manager on configure."""

    def __init__(self) -> None:
        """Initialise with no config or device_manager."""
        self.config: object = None
        self.device_manager: object = None

    def refresh_cmdline_args(self) -> None:
        """No-op."""

    def resolve(self, payload: dict[str, Any]) -> object:  # noqa: ARG002
        """Set config.

        :param payload: ignored
        :type payload: dict[str, Any]
        :return: placeholder config
        :rtype: object
        """
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Install the fake LAN device manager.

        :return: the fake device manager
        :rtype: object
        """
        self.device_manager = _FakeLANDeviceManager()
        return self.device_manager

    def boot_blocking(self) -> None:
        """No-op boot."""

    def release(self, deployment_status: dict[str, Any]) -> None:
        """No-op release.

        :param deployment_status: ignored
        :type deployment_status: dict[str, Any]
        """


class _FakeRuntimeNoDevices:
    """RuntimeContext stand-in that never sets device_manager (stays None)."""

    def __init__(self) -> None:
        """Initialise with no config or device_manager."""
        self.config: object = None
        self.device_manager: object = None

    def refresh_cmdline_args(self) -> None:
        """No-op."""

    def resolve(self, payload: dict[str, Any]) -> object:  # noqa: ARG002
        """Set config.

        :param payload: ignored
        :type payload: dict[str, Any]
        :return: placeholder config
        :rtype: object
        """
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Do NOT set device_manager (stays None).

        :return: None
        :rtype: object
        """
        return None

    def boot_blocking(self) -> None:
        """No-op boot."""

    def release(self, deployment_status: dict[str, Any]) -> None:
        """No-op release.

        :param deployment_status: ignored
        :type deployment_status: dict[str, Any]
        """


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="booted_client")
def booted_client_fixture(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a client whose session has a booted LAN device.

    configure() + boot() are called so device_manager is populated.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :yield: test client
    :rtype: TestClient
    """

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=_FakeRuntimeWithLAN())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    with TestClient(application) as client:
        client.post(
            "/session/config",
            json={"payload": {"inventory": {}, "env": {}}, "options": {}},
        )
        client.post("/session/boot")  # sync — moves to READY
        yield client


@pytest.fixture(name="unbooted_client")
def unbooted_client_fixture(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a client whose session has never been configured.

    device_manager stays None so _resolve raises 409.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :yield: test client
    :rtype: TestClient
    """

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=_FakeRuntimeNoDevices())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    with TestClient(application) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests — ping
# ---------------------------------------------------------------------------


def test_lan_ping_sync_returns_true(booted_client: TestClient) -> None:
    """Sync ping returns {"result": true}.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post("/core/templates/lan/ping", json={"ping_ip": "8.8.8.8"})
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"result": True}


def test_lan_ping_explicit_index_zero_same_as_shorthand(
    booted_client: TestClient,
) -> None:
    """Explicit index 0 and the shorthand path are equivalent.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    shorthand = booted_client.post(
        "/core/templates/lan/ping", json={"ping_ip": "8.8.8.8"}
    )
    explicit = booted_client.post(
        "/core/templates/lan/0/ping", json={"ping_ip": "8.8.8.8"}
    )
    assert shorthand.status_code == HTTP_OK
    assert explicit.status_code == HTTP_OK
    assert shorthand.json() == explicit.json()


def test_lan_ping_async_returns_202_and_job_id(booted_client: TestClient) -> None:
    """Async ping returns 202 with a job_id string.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post(
        "/core/templates/lan/ping?mode=async", json={"ping_ip": "8.8.8.8"}
    )
    assert resp.status_code == HTTP_ACCEPTED
    data = resp.json()
    assert "job_id" in data
    assert data["job_id"].startswith("j-")
    assert "state" in data


def test_lan_ping_wrong_index_returns_404(booted_client: TestClient) -> None:
    """Requesting index 1 when only one LAN device exists returns 404.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post("/core/templates/lan/1/ping", json={"ping_ip": "8.8.8.8"})
    assert resp.status_code == HTTP_NOT_FOUND


def test_lan_ping_unbooted_session_returns_409(unbooted_client: TestClient) -> None:
    """Calling a template route before the session is booted returns 409.

    :param unbooted_client: test client whose session has no device_manager
    :type unbooted_client: TestClient
    """
    resp = unbooted_client.post("/core/templates/lan/ping", json={"ping_ip": "8.8.8.8"})
    assert resp.status_code == HTTP_CONFLICT


# ---------------------------------------------------------------------------
# Tests — get_interface_macaddr
# ---------------------------------------------------------------------------


def test_lan_get_interface_macaddr_sync(booted_client: TestClient) -> None:
    """get_interface_macaddr returns the MAC in {"result": str}.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post(
        "/core/templates/lan/get_interface_macaddr", json={"interface": "eth0"}
    )
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"result": "aa:bb:cc:dd:ee:ff"}


def test_lan_get_interface_macaddr_async(booted_client: TestClient) -> None:
    """Async get_interface_macaddr returns 202 with a job_id.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post(
        "/core/templates/lan/get_interface_macaddr?mode=async",
        json={"interface": "eth0"},
    )
    assert resp.status_code == HTTP_ACCEPTED
    assert resp.json()["job_id"].startswith("j-")


# ---------------------------------------------------------------------------
# Tests — get_interface_ipv4addr
# ---------------------------------------------------------------------------


def test_lan_get_interface_ipv4addr_sync(booted_client: TestClient) -> None:
    """get_interface_ipv4addr returns the IPv4 address in {"result": str}.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post(
        "/core/templates/lan/get_interface_ipv4addr", json={"interface": "eth0"}
    )
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"result": "192.168.1.100"}


def test_lan_get_interface_ipv4addr_wrong_index_returns_404(
    booted_client: TestClient,
) -> None:
    """Index out of range on get_interface_ipv4addr returns 404.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post(
        "/core/templates/lan/99/get_interface_ipv4addr", json={"interface": "eth0"}
    )
    assert resp.status_code == HTTP_NOT_FOUND


# ---------------------------------------------------------------------------
# Tests — set_link_state
# ---------------------------------------------------------------------------


def test_lan_set_link_state_sync_returns_null_result(
    booted_client: TestClient,
) -> None:
    """set_link_state returns {"result": null} when the method returns None.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post(
        "/core/templates/lan/set_link_state",
        json={"interface": "eth0", "state": "up"},
    )
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"result": None}


def test_lan_set_link_state_async(booted_client: TestClient) -> None:
    """Async set_link_state returns 202 with a job_id.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.post(
        "/core/templates/lan/set_link_state?mode=async",
        json={"interface": "eth0", "state": "down"},
    )
    assert resp.status_code == HTTP_ACCEPTED
    assert resp.json()["job_id"].startswith("j-")


# ---------------------------------------------------------------------------
# Tests — namespace + docstring + diagnostics
# ---------------------------------------------------------------------------


def test_namespace_prefix_applied(booted_client: TestClient) -> None:
    """Routes appear under /core/templates/lan/, not bare /templates/lan/.

    :param booted_client: test client with booted session
    :type booted_client: TestClient
    """
    schema = booted_client.get("/openapi.json").json()
    paths = list(schema["paths"].keys())
    assert any("/core/templates/lan/" in p for p in paths)
    assert not any(p.startswith("/templates/lan/") for p in paths)


def test_namespace_prefix_absent_for_bare_templates(booted_client: TestClient) -> None:
    """Bare /templates/lan/ paths are absent — namespace is always applied.

    :param booted_client: test client with booted session
    :type booted_client: TestClient
    """
    schema = booted_client.get("/openapi.json").json()
    for path in schema["paths"]:
        assert not path.startswith("/templates/lan/"), (
            f"Bare template path leaked into schema: {path}"
        )


def test_openapi_descriptions_have_no_sphinx_params(booted_client: TestClient) -> None:
    """No operation description contains raw Sphinx field markers.

    :param booted_client: test client with booted session
    :type booted_client: TestClient
    """
    schema = booted_client.get("/openapi.json").json()
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            desc = operation.get("description", "")
            assert ":param" not in desc, (
                f"Sphinx :param found in {method.upper()} {path}: {desc!r}"
            )
            assert ":rtype" not in desc, (
                f"Sphinx :rtype found in {method.upper()} {path}: {desc!r}"
            )


def test_skipped_routes_endpoint(booted_client: TestClient) -> None:
    """GET /diagnostics/skipped-routes returns a list of skipped methods.

    :param booted_client: test client with booted session
    :type booted_client: TestClient
    """
    resp = booted_client.get("/diagnostics/skipped-routes")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert "skipped" in data
    assert isinstance(data["skipped"], list)
    # Each entry must have the three required keys
    for entry in data["skipped"]:
        assert "template" in entry
        assert "method" in entry
        assert "reason" in entry


def test_skipped_routes_contains_non_serialisable_lan_methods(
    booted_client: TestClient,
) -> None:
    """Skipped list includes LAN methods with non-serialisable return types.

    Methods like get_default_gateway (-> IPv4Address) or http_get (-> HTTPResult)
    cannot be auto-generated and must appear in the skipped list.

    :param booted_client: test client with a booted LAN device
    :type booted_client: TestClient
    """
    resp = booted_client.get("/diagnostics/skipped-routes")
    data = resp.json()
    skipped_methods = {entry["method"] for entry in data["skipped"]}
    assert "get_default_gateway" in skipped_methods or "http_get" in skipped_methods, (
        f"Expected at least one non-serialisable LAN method in skipped list, got: {skipped_methods}"
    )
