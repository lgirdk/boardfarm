"""Unit tests for the response adapter seam."""

from __future__ import annotations

from enum import Enum
from typing import Any

import pytest

from boardfarm3.api.routers.adapter import (
    DefaultAdapter,
    Outcome,
    Unsupported,
)

HTTP_ACCEPTED = 202


class _Colour(Enum):
    """Enum used to prove coercion is wired to the real helper."""

    RED = 1
    BLUE = 2


class _FakeJob:
    """Job stand-in carrying only what _async_response reads."""

    def __init__(self) -> None:
        self.id = "j-1"

        class _State:
            value = "queued"

        self.state = _State()


def test_default_field_spec_substitutes_enum_with_literal() -> None:
    spec = DefaultAdapter().field_spec_for("colour", _Colour, ...)
    assert not isinstance(spec, Unsupported)
    field_type, default = spec
    assert field_type is not _Colour
    assert default is ...


def test_default_field_spec_preserves_default() -> None:
    _, default = DefaultAdapter().field_spec_for("count", int, 4)
    assert default == 4


def test_default_field_spec_never_returns_unsupported() -> None:
    spec = DefaultAdapter().field_spec_for("payload", dict[str, str], ...)
    assert not isinstance(spec, Unsupported)


def test_default_coerce_turns_enum_name_into_member() -> None:
    assert DefaultAdapter().coerce("RED", _Colour) is _Colour.RED


def test_default_extra_fields_is_empty() -> None:
    assert DefaultAdapter().extra_fields() == {}


def test_default_check_request_never_short_circuits() -> None:
    assert DefaultAdapter().check_request(object(), frozenset({"a"})) is None


def test_default_supports_async_is_true() -> None:
    assert DefaultAdapter().supports_async is True


def test_default_respond_sync_wraps_value() -> None:
    outcome = Outcome(job=None, value=7, error=None, mode="sync")
    assert DefaultAdapter().respond(outcome) == {"result": 7}


def test_default_respond_async_returns_202_job_ticket() -> None:
    outcome = Outcome(job=_FakeJob(), value=None, error=None, mode="async")
    response = DefaultAdapter().respond(outcome)
    assert response.status_code == HTTP_ACCEPTED


def test_default_respond_reraises_error() -> None:
    boom = ValueError("boom")
    outcome = Outcome(job=None, value=None, error=boom, mode="sync")
    with pytest.raises(ValueError, match="boom"):
        DefaultAdapter().respond(outcome)


def test_unsupported_carries_reason() -> None:
    assert Unsupported("non-flat parameter").reason == "non-flat parameter"


def test_outcome_fields_round_trip() -> None:
    job: Any = _FakeJob()
    outcome = Outcome(job=job, value=1, error=None, mode="sync")
    assert (outcome.job, outcome.value, outcome.error, outcome.mode) == (
        job,
        1,
        None,
        "sync",
    )
