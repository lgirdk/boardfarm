"""Control plane entry point."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import uvicorn

from boardfarm3_control.app import create_app
from boardfarm3_control.hosts import HostRegistry
from boardfarm3_control.identity import resolve_control_id
from boardfarm3_control.launcher import MultiHostLauncher, ProcessLauncher
from boardfarm3_control.launcher.docker import DEFAULT_PULL_TIMEOUT
from boardfarm3_control.launcher.docker_host import (
    DEFAULT_TIMEOUT,
    DEFAULT_WORKERS,
    DockerHost,
)
from boardfarm3_control.store import store_root

if TYPE_CHECKING:
    from boardfarm3_control.models import HostSpec

_LAUNCHERS = ("docker", "process")


def _json_env(value: str, name: str) -> Any:  # noqa: ANN401
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        msg = f"{name} is not valid JSON: {exc}"
        raise ValueError(msg) from exc


def _hosts_seed() -> Any:  # noqa: ANN401
    inline = os.environ.get("BOARDFARM_HOSTS", "").strip()
    path = os.environ.get("BOARDFARM_HOSTS_FILE", "").strip()
    if inline and path:
        msg = "set BOARDFARM_HOSTS or BOARDFARM_HOSTS_FILE, not both"
        raise ValueError(msg)
    if inline:
        return _json_env(inline, "BOARDFARM_HOSTS")
    if path:
        return _json_env(Path(path).read_text(encoding="utf-8"), "BOARDFARM_HOSTS_FILE")
    return None


def _number_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _multihost_launcher() -> MultiHostLauncher:
    root = store_root()
    default_registry = os.environ.get("BOARDFARM_DEFAULT_REGISTRY", "").strip() or None
    workers = int(_number_env("BOARDFARM_HOST_WORKERS", DEFAULT_WORKERS))
    timeout = _number_env("BOARDFARM_DOCKER_TIMEOUT", DEFAULT_TIMEOUT)

    def host_factory(name: str, spec: HostSpec) -> DockerHost:
        return DockerHost(
            name,
            spec,
            default_registry=default_registry,
            workers=workers,
            timeout=timeout,
        )

    hosts = HostRegistry.load(
        root / "hosts.json",
        seed=_hosts_seed(),
        host_factory=host_factory,
    )
    return MultiHostLauncher(
        hosts,
        resolve_control_id(root),
        root / "sessions.json",
        pull_timeout=_number_env("BOARDFARM_PULL_TIMEOUT", DEFAULT_PULL_TIMEOUT),
    )


def main() -> None:
    """Run the control plane under uvicorn.

    :raises ValueError: when BOARDFARM_PROFILES is absent/invalid,
        BOARDFARM_LAUNCHER names an unknown launcher, or the hosts seed is invalid.
    """
    launcher_name = os.environ.get("BOARDFARM_LAUNCHER", "docker").lower()
    if launcher_name not in _LAUNCHERS:
        msg = (
            f"BOARDFARM_LAUNCHER must be one of: {', '.join(_LAUNCHERS)};"
            f" got {launcher_name!r}"
        )
        raise ValueError(msg)

    profiles_raw = os.environ.get("BOARDFARM_PROFILES", "")
    if not profiles_raw:
        msg = "BOARDFARM_PROFILES must be set (JSON: {profile: image, ...})"
        raise ValueError(msg)
    profiles: dict[str, str] = _json_env(profiles_raw, "BOARDFARM_PROFILES")

    cors_origins = [
        origin.strip()
        for origin in os.environ.get("BOARDFARM_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]

    launcher = _multihost_launcher() if launcher_name == "docker" else ProcessLauncher()
    app = create_app(launcher=launcher, profiles=profiles, cors_origins=cors_origins)
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104
        port=int(os.environ.get("BOARDFARM_CONTROL_PORT", "9000")),
        # Terminal keepalive: matches the agent, so a dead browser tab is
        # dropped (and its upstream relay closed) within ~60 s.
        ws_ping_interval=20.0,
        ws_ping_timeout=40.0,
    )


if __name__ == "__main__":
    main()
