"""Automated testing of network devices."""

__version__ = "2025.12.32a1"

from pluggy import HookimplMarker, HookspecMarker

PROJECT_NAME = "boardfarm"

hookspec = HookspecMarker(PROJECT_NAME)
hookimpl = HookimplMarker(PROJECT_NAME)


__all__ = ["hookimpl", "hookspec"]
