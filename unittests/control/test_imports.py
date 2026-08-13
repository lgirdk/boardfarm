"""Smoke tests for boardfarm3_control models."""

import pytest
from pydantic import ValidationError

from boardfarm3_control.models import (
    AgentInfo,
    SessionCreate,
    SessionListResponse,
    SessionResponse,
)


def test_models_importable() -> None:
    """Test that models can be imported and instantiated."""
    info = AgentInfo(
        session_id="s-abc",
        board_name="board-1",
        runtime_profile="prplos",
        container_id="c-1",
        host_port=18000,
        created_at=0.0,
    )
    assert info.session_id == "s-abc"


def test_session_create_rejects_extra_fields() -> None:
    """Test that SessionCreate rejects extra fields."""
    with pytest.raises(ValidationError):
        SessionCreate(
            board_name="b",
            runtime_profile="p",
            payload={},
            unknown_field="x",  # type: ignore
        )
