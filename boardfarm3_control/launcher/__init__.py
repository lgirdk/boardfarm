"""Agent launchers: the protocol and its fake, process, Docker and multi-host implementations."""

from __future__ import annotations

from boardfarm3_control.launcher.docker import DockerLauncher
from boardfarm3_control.launcher.fake import FakeLauncher
from boardfarm3_control.launcher.multihost import MultiHostLauncher
from boardfarm3_control.launcher.process import ProcessLauncher
from boardfarm3_control.launcher.protocol import Launcher

__all__ = [
    "DockerLauncher",
    "FakeLauncher",
    "Launcher",
    "MultiHostLauncher",
    "ProcessLauncher",
]
