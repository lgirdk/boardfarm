"""Tests that a custom adapter changes use-case route behaviour."""

from __future__ import annotations

import inspect
import types as _types
from typing import Any

from boardfarm3.api.routers._usecase_generator import (
    _build_request_model,
    generate_usecase_routers,
)
from boardfarm3.api.routers.adapter import DefaultAdapter, Unsupported


class _RejectDictAdapter(DefaultAdapter):
    """Adapter that refuses dict-valued parameters and adds a tracking field."""

    def field_spec_for(
        self,
        name: str,
        annotation: Any,
        default: Any,
    ) -> tuple[Any, Any] | Unsupported:
        """Reject dict annotations, else defer to the default.

        :param name: parameter name
        :type name: str
        :param annotation: parameter annotation
        :type annotation: Any
        :param default: parameter default
        :type default: Any
        :return: field spec or Unsupported
        :rtype: tuple[Any, Any] | Unsupported
        """
        if annotation is dict or getattr(annotation, "__origin__", None) is dict:
            return Unsupported("non-flat parameter")
        return super().field_spec_for(name, annotation, default)

    def extra_fields(self) -> dict[str, tuple[Any, Any]]:
        """Add one optional correlation field.

        :return: the extra field mapping
        :rtype: dict[str, tuple[Any, Any]]
        """
        return {"trace_id": (str | None, None)}


class _SyncOnlyAdapter(DefaultAdapter):
    """Adapter that disables async dispatch."""

    supports_async = False


def _module() -> _types.ModuleType:
    mod = _types.ModuleType("fake_uc")

    def simple(host: str, count: int = 1) -> str:
        """Do a simple thing.

        :param host: target host
        :type host: str
        :param count: how many
        :type count: int
        :return: a message
        :rtype: str
        """
        return f"{host}:{count}"

    def nested(payload: dict[str, str]) -> str:
        """Do a nested thing.

        :param payload: nested mapping
        :type payload: dict[str, str]
        :return: a message
        :rtype: str
        """
        return str(payload)

    simple.__module__ = "fake_uc"
    nested.__module__ = "fake_uc"
    mod.simple = simple  # type: ignore[attr-defined]
    mod.nested = nested  # type: ignore[attr-defined]
    return mod


def test_unsupported_param_skips_the_use_case() -> None:
    routers, skipped = generate_usecase_routers(
        [_module()], adapter=_RejectDictAdapter()
    )
    paths = {r.path for r in routers[0].routes}  # type: ignore[attr-defined]
    assert not any(p.endswith("/nested") for p in paths)
    assert ("nested", "non-flat parameter") in {(s.method, s.reason) for s in skipped}


def test_supported_use_case_still_generates() -> None:
    routers, _ = generate_usecase_routers([_module()], adapter=_RejectDictAdapter())
    paths = {r.path for r in routers[0].routes}  # type: ignore[attr-defined]
    assert any(p.endswith("/simple") for p in paths)


def test_extra_fields_appear_on_the_use_case_model() -> None:
    sig = inspect.signature(_module().simple, eval_str=True)
    result = _build_request_model("simple", sig, adapter=_RejectDictAdapter())
    assert not isinstance(result, Unsupported)
    model, _ = result
    assert "trace_id" in model.model_fields


def test_default_adapter_use_case_model_has_no_extra_fields() -> None:
    sig = inspect.signature(_module().simple, eval_str=True)
    result = _build_request_model("simple", sig)
    assert not isinstance(result, Unsupported)
    model, _ = result
    assert set(model.model_fields) == {"host", "count"}


def test_sync_only_adapter_removes_mode_from_use_case_signature() -> None:
    routers, _ = generate_usecase_routers([_module()], adapter=_SyncOnlyAdapter())
    route = next(
        r
        for r in routers[0].routes
        if getattr(r, "path", "").endswith("/simple")  # type: ignore[arg-type]
    )
    assert "mode" not in inspect.signature(route.endpoint).parameters  # type: ignore[attr-defined]


class _CollidingAdapter(DefaultAdapter):
    """Adapter whose extra field collides with a real parameter name."""

    def extra_fields(self) -> dict[str, tuple[Any, Any]]:
        """Inject a field that shadows ``simple``'s ``host`` param.

        :return: the extra field mapping
        :rtype: dict[str, tuple[Any, Any]]
        """
        return {"host": (str | None, None)}


def test_extra_field_collision_skips_the_use_case_instead_of_clobbering() -> None:
    sig = inspect.signature(_module().simple, eval_str=True)
    result = _build_request_model("simple", sig, adapter=_CollidingAdapter())
    assert isinstance(result, Unsupported)
    assert result.reason == "extra field collides with parameter 'host'"


def test_extra_field_collision_is_reported_by_the_use_case_generator() -> None:
    routers, skipped = generate_usecase_routers(
        [_module()], adapter=_CollidingAdapter()
    )
    paths = {r.path for r in routers[0].routes}  # type: ignore[attr-defined]
    assert not any(p.endswith("/simple") for p in paths)
    reasons = {(s.method, s.reason) for s in skipped}
    assert ("simple", "extra field collides with parameter 'host'") in reasons
