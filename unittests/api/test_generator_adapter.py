"""Tests that a custom adapter changes template route behaviour."""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any

from fastapi import APIRouter  # noqa: TC002

from boardfarm3.api.routers._generator import (
    _make_request_model,
    generate_template_routers,
)
from boardfarm3.api.routers.adapter import DefaultAdapter, Outcome, Unsupported


class _Widget(ABC):
    """Template ABC used only by these tests."""

    @abstractmethod
    def poke(self, label: str, times: int = 1) -> str:
        """Poke the widget.

        :param label: what to poke
        :type label: str
        :param times: how often
        :type times: int
        :return: a message
        :rtype: str
        """

    @abstractmethod
    def bulk(self, payload: dict[str, str]) -> str:
        """Accept a nested payload.

        :param payload: nested mapping
        :type payload: dict[str, str]
        :return: a message
        :rtype: str
        """


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


class _AbsorbingAdapter(DefaultAdapter):
    """Adapter that converts every failure into a 200 body."""

    def respond(self, outcome: Outcome) -> Any:
        """Return a flat body instead of raising.

        :param outcome: dispatch outcome
        :type outcome: Outcome
        :return: a plain dict
        :rtype: Any
        """
        if outcome.error is not None:
            return {"ok": False, "why": str(outcome.error)}
        return {"ok": True, "value": outcome.value}


def _routes(router: APIRouter) -> set[str]:
    return {r.path for r in router.routes}  # type: ignore[attr-defined]


def test_unsupported_param_skips_the_whole_method() -> None:
    routers, skipped = generate_template_routers(
        [_Widget], adapter=_RejectDictAdapter()
    )
    assert not any("/bulk" in path for path in _routes(routers[0]))
    reasons = {(s.method, s.reason) for s in skipped}
    assert ("bulk", "non-flat parameter") in reasons


def test_supported_methods_still_generate_with_custom_adapter() -> None:
    routers, _ = generate_template_routers([_Widget], adapter=_RejectDictAdapter())
    assert any(path.endswith("/poke") for path in _routes(routers[0]))


def test_extra_fields_appear_on_the_request_model() -> None:
    sig = inspect.signature(_Widget.poke, eval_str=True)
    result = _make_request_model("poke", sig, adapter=_RejectDictAdapter())
    assert not isinstance(result, Unsupported)
    model, _ = result
    assert "trace_id" in model.model_fields


def test_default_adapter_request_model_has_no_extra_fields() -> None:
    sig = inspect.signature(_Widget.poke, eval_str=True)
    result = _make_request_model("poke", sig)
    assert not isinstance(result, Unsupported)
    model, _ = result
    assert set(model.model_fields) == {"label", "times"}


def test_sync_only_adapter_removes_mode_from_the_signature() -> None:
    routers, _ = generate_template_routers([_Widget], adapter=_SyncOnlyAdapter())
    route = next(
        r
        for r in routers[0].routes
        if getattr(r, "path", "").endswith("/poke")  # type: ignore[arg-type]
    )
    params = inspect.signature(route.endpoint).parameters  # type: ignore[attr-defined]
    assert "mode" not in params


def test_default_adapter_keeps_mode_in_the_signature() -> None:
    routers, _ = generate_template_routers([_Widget])
    route = next(
        r
        for r in routers[0].routes
        if getattr(r, "path", "").endswith("/poke")  # type: ignore[arg-type]
    )
    params = inspect.signature(route.endpoint).parameters  # type: ignore[attr-defined]
    assert "mode" in params


def test_absorbing_adapter_is_accepted_by_the_generator() -> None:
    routers, skipped = generate_template_routers([_Widget], adapter=_AbsorbingAdapter())
    assert any(path.endswith("/poke") for path in _routes(routers[0]))
    assert all(s.method != "poke" for s in skipped)
