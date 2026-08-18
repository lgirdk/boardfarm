"""Unit tests for the template router generator."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

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
    route_paths = [r.path for r in router.routes]
    assert "/greet" in route_paths
    assert "/{index}/greet" in route_paths
    greet_skipped = [s for s in skipped if s.method == "greet"]
    assert greet_skipped == []


def test_returns_none_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsNone])
    paths = [r.path for r in routers[0].routes]
    assert "/reset" in paths


def test_returns_bool_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsBool])
    paths = [r.path for r in routers[0].routes]
    assert "/check" in paths


def test_returns_dict_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsDict])
    paths = [r.path for r in routers[0].routes]
    assert "/info" in paths


def test_returns_list_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsList])
    paths = [r.path for r in routers[0].routes]
    assert "/items" in paths


def test_returns_union_str_none_generates_route() -> None:
    routers, _ = generate_template_routers([_ReturnsUnion])
    paths = [r.path for r in routers[0].routes]
    assert "/maybe" in paths


def test_lan_template_generates_all_serialisable_routes() -> None:
    from boardfarm3.templates.lan import LAN

    routers, _skipped = generate_template_routers([LAN])
    assert len(routers) == 1
    paths = {r.path for r in routers[0].routes}
    # These four were in the hand-written lan.py — must still be present
    assert "/ping" in paths
    assert "/{index}/ping" in paths
    assert "/get_interface_macaddr" in paths
    assert "/get_interface_ipv4addr" in paths
    assert "/set_link_state" in paths
    # Properties must not appear
    assert "/iface_dut" not in paths
    assert "/console" not in paths
