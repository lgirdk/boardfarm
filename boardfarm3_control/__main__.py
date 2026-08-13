"""Control plane entry point."""

from __future__ import annotations

import json
import os

import uvicorn

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import DockerLauncher


def main() -> None:
    """Run the control plane under uvicorn.

    :raises ValueError: when BOARDFARM_PROFILES is absent or invalid JSON
    """
    profiles_raw = os.environ.get("BOARDFARM_PROFILES", "")
    if not profiles_raw:
        msg = "BOARDFARM_PROFILES must be set (JSON: {profile: image, ...})"
        raise ValueError(msg)
    try:
        profiles: dict[str, str] = json.loads(profiles_raw)
    except json.JSONDecodeError as exc:
        msg = f"BOARDFARM_PROFILES is not valid JSON: {exc}"
        raise ValueError(msg) from exc

    app = create_app(launcher=DockerLauncher(), profiles=profiles)
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104
        port=int(os.environ.get("BOARDFARM_CONTROL_PORT", "9000")),
    )


if __name__ == "__main__":
    main()
