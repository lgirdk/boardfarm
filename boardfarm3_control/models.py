"""Pydantic request/response models for the boardfarm control plane."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentInfo(BaseModel):
    """Per-session runtime info stored in the registry and returned by launchers."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    board_name: str
    runtime_profile: str
    container_id: str
    host_port: int
    created_at: float
    pid: int | None = None
    agent_url: str = ""


class SessionCreate(BaseModel):
    """Body of POST /sessions."""

    model_config = ConfigDict(extra="forbid")

    board_name: str
    runtime_profile: str
    payload: dict[str, Any]
    options: dict[str, Any] = Field(default_factory=dict)
    boot: bool = False


class SessionResponse(BaseModel):
    """Response body for POST /sessions and per-item in GET /sessions."""

    session_id: str
    board_name: str
    runtime_profile: str
    state: str
    boot_job_id: str | None = None
    booted: bool = False
    agent_url: str = ""
    pid: int | None = None
    created_at: float
    last_activity: float | None = None


class SessionListResponse(BaseModel):
    """Response body for GET /sessions."""

    sessions: list[SessionResponse]
    total: int
    offset: int
    limit: int
