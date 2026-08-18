"""Unit tests for the template router generator."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from fastapi import APIRouter

from boardfarm3.api.routers._generator import generate_template_routers

# ---------------------------------------------------------------------------
# Minimal ABCs for testing
# ---------------------------------------------------------------------------


class _SimpleABC:
    @abstractmethod
    def greet(self, name: str) -> str: ...

    @abstractmethod
    def _private(self) -> str: ...  # skip: private

    @property
    @abstractmethod
    def label(self) -> str: ...  # skip: property

    @abstractmethod
    def complex_return(self) -> object: ...  # skip: non-serialisable return

    @abstractmethod
    def no_annotation(self, x) -> str: ...  # noqa: ANN001  # skip: missing param annotation


class _ReturnsNone:
    @abstractmethod
    def reset(self) -> None: ...


class _ReturnsBool:
    @abstractmethod
    def check(self) -> bool: ...


class _ReturnsDict:
    @abstractmethod
    def info(self) -> dict[str, Any]: ...


class _ReturnsList:
    @abstractmethod
    def items(self) -> list[str]: ...


class _ReturnsUnion:
    @abstractmethod
    def maybe(self) -> str | None: ...


# ---------------------------------------------------------------------------
# Helper: strip the router prefix so assertions use short method paths
# ---------------------------------------------------------------------------


def _local_paths(router: object) -> list[str]:
    """Return route paths relative to the router prefix.

    FastAPI 0.141+ stores the full ``prefix + path`` in ``route.path``,
    so we strip the prefix to get the method-local portion (e.g. ``/ping``).

    :param router: an APIRouter returned by generate_template_routers
    :type router: object
    :return: list of local route paths
    :rtype: list[str]
    """
    pfx: str = getattr(router, "prefix", "") or ""
    return [r.path.removeprefix(pfx) for r in router.routes]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Skip rule tests
# ---------------------------------------------------------------------------


def test_private_method_skipped() -> None:
    _, skipped = generate_template_routers([_SimpleABC])
    names = [s.method for s in skipped]
    assert "_private" in names
    found = next(s for s in skipped if s.method == "_private")
    assert found.reason == "private"


def test_property_skipped() -> None:
    _, skipped = generate_template_routers([_SimpleABC])
    names = [s.method for s in skipped]
    assert "label" in names


def test_non_serialisable_return_skipped() -> None:
    _, skipped = generate_template_routers([_SimpleABC])
    found = next((s for s in skipped if s.method == "complex_return"), None)
    assert found is not None
    assert "serialis" in found.reason.lower()


def test_missing_param_annotation_skipped() -> None:
    _, skipped = generate_template_routers([_SimpleABC])
    found = next((s for s in skipped if s.method == "no_annotation"), None)
    assert found is not None


# ---------------------------------------------------------------------------
# Route generation tests
# ---------------------------------------------------------------------------


def test_public_serialisable_method_generates_route() -> None:
    routers, skipped = generate_template_routers([_SimpleABC])
    assert len(routers) == 1
    router = routers[0]
    route_paths = _local_paths(router)
    assert "/greet" in route_paths
    assert "/{index}/greet" in route_paths
    greet_skipped = [s for s in skipped if s.method == "greet"]
    assert greet_skipped == []


def test_returns_none_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsNone])
    paths = _local_paths(routers[0])
    assert "/reset" in paths


def test_returns_bool_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsBool])
    paths = _local_paths(routers[0])
    assert "/check" in paths


def test_returns_dict_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsDict])
    paths = _local_paths(routers[0])
    assert "/info" in paths


def test_returns_list_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsList])
    paths = _local_paths(routers[0])
    assert "/items" in paths


def test_returns_union_str_none_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsUnion])
    paths = _local_paths(routers[0])
    assert "/maybe" in paths


def test_lan_template_generates_all_serialisable_routes() -> None:
    from boardfarm3.templates.lan import LAN

    routers, _skipped = generate_template_routers([LAN])
    assert len(routers) == 1
    paths = set(_local_paths(routers[0]))
    # These four were in the hand-written lan.py — must still be present
    assert "/ping" in paths
    assert "/{index}/ping" in paths
    assert "/get_interface_macaddr" in paths
    assert "/get_interface_ipv4addr" in paths
    assert "/set_link_state" in paths
    # Properties must not appear
    assert "/iface_dut" not in paths
    assert "/console" not in paths


def test_routerbundle_wraps_routers_under_namespace() -> None:
    """RouterBundle namespace is prepended by load_plugin_routers.

    :return: None
    :rtype: None
    """
    from unittest.mock import MagicMock, patch

    from boardfarm3.api.routers import RouterBundle, load_plugin_routers

    inner = APIRouter(prefix="/templates/foo")

    @inner.get("/bar")
    async def _dummy() -> dict:  # noqa: ANN201
        return {}

    bundle = RouterBundle(namespace="test_ns", routers=[inner], skipped=[])

    with patch(
        "boardfarm3.api.routers.pluggy.PluginManager"
    ) as mock_pm_cls:
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.hook.boardfarm_add_api_routers.return_value = [bundle]
        routers, skipped = load_plugin_routers()

    assert len(routers) == 1
    wrapper = routers[0]
    # Verify the namespace prefix is applied to the wrapper router
    assert wrapper.prefix == "/test_ns"
    # Verify the inner router is included (routes may be _IncludedRouter in newer FastAPI)
    assert len(wrapper.routes) > 0
    assert skipped == []
