"""Unit tests for the use-case router generator."""

from __future__ import annotations

from typing import Any, Literal

from boardfarm3.api.routers._usecase_generator import (
    _classify_param,
    _is_template,
    _template_types,
)
from boardfarm3.templates.cpe import CPE
from boardfarm3.templates.lan import LAN
from boardfarm3.templates.wan import WAN


def test_is_template_true_for_template_abc() -> None:
    assert _is_template(LAN) is True


def test_is_template_false_for_primitive() -> None:
    assert _is_template(str) is False


def test_classify_single_template_is_device() -> None:
    assert _classify_param(LAN) == "device"


def test_classify_union_of_templates_is_device() -> None:
    assert _classify_param(LAN | WAN | CPE) == "device"


def test_classify_primitive_is_primitive() -> None:
    assert _classify_param(str) == "primitive"
    assert _classify_param(int) == "primitive"


def test_classify_optional_primitive_is_primitive() -> None:
    assert _classify_param(str | None) == "primitive"


def test_classify_literal_is_primitive() -> None:
    assert _classify_param(Literal["up", "down"]) == "primitive"


def test_classify_unknown_object_is_unroutable() -> None:
    class _Weird:
        pass

    assert _classify_param(_Weird) == "unroutable"


def test_classify_type_param_is_unroutable() -> None:
    assert _classify_param(type[Any]) == "unroutable"


def test_template_types_single() -> None:
    assert _template_types(LAN) == (LAN,)


def test_template_types_union() -> None:
    assert set(_template_types(LAN | WAN)) == {LAN, WAN}


def test_generate_usecase_routers_builds_routes_and_skips() -> None:
    import types as _types

    from boardfarm3.api.routers._usecase_generator import generate_usecase_routers

    mod = _types.ModuleType("fake_uc")

    def get_cpu_usage(board: CPE) -> float:  # routable: 1 device, serialisable
        del board  # unused: only the signature matters for this test
        return 0.0

    def parse_trace(packet: object) -> list:  # unroutable param
        del packet  # unused: only the signature matters for this test
        return []

    def make_ctx(board: CPE) -> Any:  # non-serialisable return
        return board

    get_cpu_usage.__module__ = "boardfarm3.use_cases.fake_uc"
    parse_trace.__module__ = "boardfarm3.use_cases.fake_uc"
    make_ctx.__module__ = "boardfarm3.use_cases.fake_uc"
    mod.get_cpu_usage = get_cpu_usage
    mod.parse_trace = parse_trace
    mod.make_ctx = make_ctx
    mod.__name__ = "boardfarm3.use_cases.fake_uc"

    routers, skipped = generate_usecase_routers([mod])
    assert len(routers) == 1
    assert routers[0].prefix == "/use_cases/fake_uc"
    paths = [r.path.removeprefix(routers[0].prefix) for r in routers[0].routes]
    assert "/get_cpu_usage" in paths
    skipped_names = {s.method for s in skipped}
    assert "parse_trace" in skipped_names  # unroutable param
    assert "make_ctx" in skipped_names  # non-serialisable return
