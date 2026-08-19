"""Unit tests for the template router generator."""

from __future__ import annotations

from abc import abstractmethod
from enum import Enum
from typing import Any, TypedDict

from fastapi import APIRouter

from boardfarm3.api.routers._generator import (
    _annotation_to_field_type,
    _coerce,
    _CoercionPlan,
    _is_serialisable,
    _parse_sphinx_params,
    generate_template_routers,
)

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


def test_template_mount_flattens_two_introspect_sources() -> None:
    from boardfarm3.api.routers._generator import (
        TemplateMount,
        generate_template_routers,
    )

    class _Sw:
        @abstractmethod
        def reset(self) -> None: ...

    class _Hw:
        @abstractmethod
        def power_cycle(self) -> None: ...

    class _Composite:
        pass

    mounts = [
        TemplateMount("cpe", _Composite, _Sw, "sw"),
        TemplateMount("cpe", _Composite, _Hw, "hw"),
    ]
    routers, _ = generate_template_routers(mounts)
    assert len(routers) == 1  # both specs merge into ONE mount router
    assert routers[0].prefix == "/templates/cpe"
    paths = set(_local_paths(routers[0]))
    assert "/reset" in paths  # from _Sw via .sw
    assert "/power_cycle" in paths  # from _Hw via .hw


def test_template_mount_duplicate_name_skipped() -> None:
    from boardfarm3.api.routers._generator import (
        TemplateMount,
        generate_template_routers,
    )

    class _A:
        @abstractmethod
        def dup(self) -> None: ...

    class _B:
        @abstractmethod
        def dup(self) -> None: ...

    class _C:
        pass

    routers, skipped = generate_template_routers(
        [TemplateMount("x", _C, _A, "a"), TemplateMount("x", _C, _B, "b")]
    )
    paths = _local_paths(routers[0])
    assert paths.count("/dup") == 1  # only first wins (plus its /{index}/dup)
    assert any(s.method == "dup" and "duplicate" in s.reason for s in skipped)


def test_cpe_flatten_exposes_sw_and_hw_methods() -> None:
    from boardfarm3.api.routers._generator import (
        TemplateMount,
        generate_template_routers,
    )
    from boardfarm3.templates.cpe import CPE, CPEHW, CPESW

    routers, _ = generate_template_routers(
        [TemplateMount("cpe", CPE, CPESW, "sw"), TemplateMount("cpe", CPE, CPEHW, "hw")]
    )
    assert len(routers) == 1
    assert routers[0].prefix == "/templates/cpe"
    paths = set(_local_paths(routers[0]))
    assert "/reset" in paths  # CPESW.reset -> None
    assert "/factory_reset" in paths  # CPESW.factory_reset -> bool
    assert "/power_cycle" in paths  # CPEHW.power_cycle -> None


def test_bare_type_still_normalises_to_router() -> None:
    routers, _ = generate_template_routers([_ReturnsBool])
    assert routers[0].prefix == "/templates/_returnsbool"
    assert "/check" in _local_paths(routers[0])


def test_routerbundle_wraps_routers_under_namespace() -> None:
    """Verify that load_plugin_routers prepends the bundle namespace prefix.

    :return: None
    :rtype: None
    """
    from unittest.mock import MagicMock, patch

    from boardfarm3.api.routers import RouterBundle, load_plugin_routers

    inner = APIRouter(prefix="/templates/foo")

    @inner.get("/bar")
    async def _dummy() -> dict:
        return {}

    bundle = RouterBundle(namespace="test_ns", routers=[inner], skipped=[])

    with patch("boardfarm3.api.routers.pluggy.PluginManager") as mock_pm_cls:
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        # pluggy collects each plugin's return value into a list, so the hook
        # call returns list[list[RouterBundle]] — one inner list per plugin.
        mock_pm.hook.boardfarm_add_api_routers.return_value = [[bundle]]
        routers, skipped = load_plugin_routers()

    assert len(routers) == 1
    wrapper = routers[0]
    # Verify the namespace prefix is applied to the wrapper router
    assert wrapper.prefix == "/test_ns"
    # Verify the inner router is included (routes may be _IncludedRouter in newer FastAPI)
    assert len(wrapper.routes) > 0
    assert skipped == []


# ---------------------------------------------------------------------------
# _is_serialisable — new cases
# ---------------------------------------------------------------------------


class _Color(Enum):
    RED = 1
    BLUE = 2


class _Coord(TypedDict):
    x: float
    y: float


def test_is_serialisable_tuple_of_primitives() -> None:
    assert _is_serialisable(tuple[str, int]) is True


def test_is_serialisable_tuple_uniform() -> None:
    assert _is_serialisable(tuple[str, ...]) is True


def test_is_serialisable_empty_tuple() -> None:
    assert _is_serialisable(tuple[()]) is True  # type: ignore[misc]


def test_is_serialisable_enum() -> None:
    assert _is_serialisable(_Color) is True


def test_is_serialisable_typeddict() -> None:
    assert _is_serialisable(_Coord) is True


def test_is_serialisable_nested_tuple_in_list() -> None:
    assert _is_serialisable(list[tuple[str, int]]) is True


def test_is_serialisable_set_remains_false() -> None:
    assert _is_serialisable(set[str]) is False  # type: ignore[type-arg]


def test_is_serialisable_typeddict_with_bad_value_false() -> None:
    class _Bad(TypedDict):
        obj: object

    assert _is_serialisable(_Bad) is False


# ---------------------------------------------------------------------------
# _annotation_to_field_type
# ---------------------------------------------------------------------------


def test_annotation_to_field_type_primitive_unchanged() -> None:
    assert _annotation_to_field_type(str) is str
    assert _annotation_to_field_type(int) is int
    assert _annotation_to_field_type(bool) is bool


def test_annotation_to_field_type_enum_becomes_literal() -> None:
    from typing import Literal, get_args, get_origin

    result = _annotation_to_field_type(_Color)
    assert get_origin(result) is Literal
    assert set(get_args(result)) == {"RED", "BLUE"}


def test_annotation_to_field_type_tuple_fixed_becomes_list_union() -> None:
    from typing import get_args, get_origin

    result = _annotation_to_field_type(tuple[str, int])
    assert get_origin(result) is list
    inner = get_args(result)[0]
    assert set(get_args(inner)) == {str, int}


def test_annotation_to_field_type_tuple_uniform_becomes_list() -> None:
    result = _annotation_to_field_type(tuple[str, ...])
    from typing import get_args, get_origin

    assert get_origin(result) is list
    assert get_args(result) == (str,)


def test_annotation_to_field_type_list_with_enum_inner() -> None:
    from typing import Literal, get_args, get_origin

    result = _annotation_to_field_type(list[_Color])
    assert get_origin(result) is list
    inner = get_args(result)[0]
    assert get_origin(inner) is Literal


def test_annotation_to_field_type_typeddict_unchanged() -> None:
    assert _annotation_to_field_type(_Coord) is _Coord


# ---------------------------------------------------------------------------
# _CoercionPlan
# ---------------------------------------------------------------------------


def test_coercion_plan_empty() -> None:
    plan = _CoercionPlan(coercions={})
    assert plan.coercions == {}


def test_coercion_plan_stores_annotations() -> None:
    plan = _CoercionPlan(coercions={"records": list[tuple[str, _Color]]})
    assert plan.coercions["records"] == list[tuple[str, _Color]]


# ---------------------------------------------------------------------------
# _coerce
# ---------------------------------------------------------------------------


def test_coerce_primitive_unchanged() -> None:
    assert _coerce("hello", str) == "hello"
    assert _coerce(42, int) == 42


def test_coerce_enum_by_name() -> None:
    assert _coerce("RED", _Color) == _Color.RED


def test_coerce_fixed_tuple() -> None:
    result = _coerce(["RED", 42], tuple[_Color, int])
    assert result == (_Color.RED, 42)
    assert isinstance(result, tuple)


def test_coerce_uniform_tuple() -> None:
    result = _coerce(["a", "b"], tuple[str, ...])
    assert result == ("a", "b")
    assert isinstance(result, tuple)


def test_coerce_list_of_enum() -> None:
    result = _coerce(["RED", "BLUE"], list[_Color])
    assert result == [_Color.RED, _Color.BLUE]


def test_coerce_nested_list_of_tuple_with_enum() -> None:
    result = _coerce([["RED", "group1"], ["BLUE", "group2"]], list[tuple[_Color, str]])
    assert result == [(_Color.RED, "group1"), (_Color.BLUE, "group2")]


def test_coerce_optional_enum_none() -> None:
    result = _coerce(None, _Color | None)
    assert result is None


def test_coerce_optional_enum_value() -> None:
    result = _coerce("RED", _Color | None)
    assert result == _Color.RED


def test_coerce_typeddict_passthrough() -> None:
    data = {"x": 1.0, "y": 2.0}
    assert _coerce(data, _Coord) == data


# ---------------------------------------------------------------------------
# _parse_sphinx_params
# ---------------------------------------------------------------------------


def test_parse_sphinx_params_basic() -> None:
    doc = """Do something.\n\n:param name: the user name\n:param count: how many\n:return: result\n"""
    result = _parse_sphinx_params(doc)
    assert result == {"name": "the user name", "count": "how many"}


def test_parse_sphinx_params_multiline_collapsed() -> None:
    doc = ":param records: a list of\n    multicast records\n:return: nothing\n"
    result = _parse_sphinx_params(doc)
    assert result["records"] == "a list of multicast records"


def test_parse_sphinx_params_none() -> None:
    assert _parse_sphinx_params(None) == {}


def test_parse_sphinx_params_no_params() -> None:
    assert _parse_sphinx_params("Just a summary.") == {}


def test_parse_sphinx_params_ignores_type_lines() -> None:
    doc = ":param x: the x value\n:type x: int\n"
    result = _parse_sphinx_params(doc)
    assert "x" in result
    assert "type x" not in result  # :type x: should not be a key
