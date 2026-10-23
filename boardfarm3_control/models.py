"""Pydantic request/response models for the boardfarm control plane."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The agent's identity: set by the launcher, never by the client. Letting a
# client override BOARDFARM_BOARD_NAME would lease one board while the agent
# drives another.
RESERVED_AGENT_ENV = frozenset(
    {"BOARDFARM_BOARD_NAME", "BOARDFARM_SESSION_ID", "BOARDFARM_AGENT_PORT"},
)


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
    state: str = "live"
    ended_at: float | None = None
    artifact_dir: str = "/var/log/boardfarm"
    host: str | None = None
    image_id: str | None = None
    stop_pending: bool = False
    mode: str = "interact"
    run: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The run's latest summary as the agent reported it (outcome, counts,"
            " selection). Null in interact mode."
        ),
    )
    created_by: str | None = None


class SessionCreate(BaseModel):
    """Body of POST /sessions."""

    model_config = ConfigDict(extra="forbid")

    board_name: str
    runtime_profile: str
    payload: dict[str, Any]
    options: dict[str, Any] = Field(default_factory=dict)
    boot: bool = False
    agent_env: dict[str, str] = Field(default_factory=dict)
    mode: str = "interact"
    run: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The run request: the test selection and arguments for the session's"
            " mode. Absent in interact mode."
        ),
    )
    created_by: str | None = None

    @field_validator("agent_env")
    @classmethod
    def no_reserved_keys(cls, value: dict[str, str]) -> dict[str, str]:
        """Reject variables that would change which board or session the agent serves.

        :param value: the requested agent environment
        :type value: dict[str, str]
        :return: the environment, unchanged
        :rtype: dict[str, str]
        :raises ValueError: when a reserved key is present
        """
        reserved = sorted(RESERVED_AGENT_ENV & value.keys())
        if reserved:
            msg = f"agent_env must not set {', '.join(reserved)}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def check_mode(self) -> SessionCreate:
        """Require a run outside interact, refuse one in it, and refuse boot with it.

        :return: the validated body
        :rtype: SessionCreate
        :raises ValueError: when mode, run and boot do not fit together
        """
        if self.mode == "interact":
            if self.run is not None:
                msg = "run is only valid when mode is not interact"
                raise ValueError(msg)
            return self
        if self.run is None:
            msg = f"mode {self.mode} needs a run"
            raise ValueError(msg)
        if self.boot:
            msg = (
                f"boot does not apply to {self.mode} sessions;"
                " set options.skip_boot instead"
            )
            raise ValueError(msg)
        return self


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
    ended_at: float | None = None
    liveness: dict[str, Any] | None = None
    host: str | None = None
    image_id: str | None = None
    stop_pending: bool = False
    warnings: list[str] = Field(default_factory=list)
    mode: str = "interact"
    run: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The run's latest summary as the agent reported it (outcome, counts,"
            " selection). Null in interact mode."
        ),
    )
    created_by: str | None = None


class SessionListResponse(BaseModel):
    """Response body for GET /sessions."""

    sessions: list[SessionResponse]
    total: int
    offset: int
    limit: int


_DOCKER_SCHEMES = ("tcp://", "unix://", "ssh://")


class HostSpec(BaseModel):
    """One lab host's record in ``hosts.json``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    docker_url: str | None = None
    advertise_addr: str | None = None
    bind_addr: str = "0.0.0.0"  # noqa: S104
    registry: str | None = None
    tls: dict[str, str] | None = None
    drain: bool = False
    default: bool = False

    @model_validator(mode="after")
    def check_fields(self) -> HostSpec:
        """Reject a TLS block, unknown URL schemes and ssh:// without an address.

        :return: the validated record
        :rtype: HostSpec
        :raises ValueError: when the record is not usable
        """
        if self.tls is not None:
            msg = "NotImplemented: tls is reserved until the security work lands"
            raise ValueError(msg)
        url = self.docker_url
        if url is not None and not url.startswith(_DOCKER_SCHEMES):
            msg = f"docker_url must start with one of {', '.join(_DOCKER_SCHEMES)}"
            raise ValueError(msg)
        if url is not None and url.startswith("ssh://") and not self.advertise_addr:
            msg = "advertise_addr is required for ssh:// hosts"
            raise ValueError(msg)
        return self

    def effective_advertise_addr(self) -> str:
        """Return the address control uses to reach agents on this host.

        :return: ``advertise_addr``, else the ``tcp://`` host, else ``localhost``
        :rtype: str
        """
        if self.advertise_addr:
            return self.advertise_addr
        if self.docker_url is None or self.docker_url.startswith("unix://"):
            return "localhost"
        return urlsplit(self.docker_url).hostname or "localhost"


class HostPatch(BaseModel):
    """Body of ``PATCH /admin/hosts/{name}``; only the fields sent change."""

    model_config = ConfigDict(extra="forbid")

    docker_url: str | None = None
    advertise_addr: str | None = None
    bind_addr: str | None = None
    registry: str | None = None
    tls: dict[str, str] | None = None
    drain: bool | None = None
    default: bool | None = None


class HostStatus(BaseModel):
    """Live status of one host."""

    breaker: str
    last_error: str | None = None
    last_ok_at: float | None = None
    sessions: dict[str, int]
    conflicts: int = 0


class HostView(BaseModel):
    """One host as returned by ``/admin/hosts``."""

    name: str
    spec: HostSpec
    effective_registry: str | None = None
    status: HostStatus
    probe: bool | None = None
