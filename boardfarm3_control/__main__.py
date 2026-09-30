"""Control plane entry point."""

from __future__ import annotations

import json
import os

import uvicorn

from boardfarm3_control.app import create_app
from boardfarm3_control.identity import resolve_control_id
from boardfarm3_control.launcher import DockerLauncher, ProcessLauncher
from boardfarm3_control.launcher.docker_host import DockerHost
from boardfarm3_control.models import HostSpec
from boardfarm3_control.store import store_root


def _docker_launcher() -> DockerLauncher:
    host = DockerHost("local", HostSpec(advertise_addr="localhost", registry=""))
    return DockerLauncher(host, resolve_control_id(store_root()))


_LAUNCHERS = {
    "docker": _docker_launcher,
    "process": ProcessLauncher,
}


def main() -> None:
    """Run the control plane under uvicorn.

    :raises ValueError: when BOARDFARM_PROFILES is absent/invalid or
        BOARDFARM_LAUNCHER names an unknown launcher.
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
    try:
        profiles: dict[str, str] = json.loads(profiles_raw)
    except json.JSONDecodeError as exc:
        msg = f"BOARDFARM_PROFILES is not valid JSON: {exc}"
        raise ValueError(msg) from exc

    cors_origins = [
        origin.strip()
        for origin in os.environ.get("BOARDFARM_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]

    app = create_app(
        launcher=_LAUNCHERS[launcher_name](),
        profiles=profiles,
        cors_origins=cors_origins,
    )
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104
        port=int(os.environ.get("BOARDFARM_CONTROL_PORT", "9000")),
    )


if __name__ == "__main__":
    main()
