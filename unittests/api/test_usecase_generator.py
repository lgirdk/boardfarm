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
