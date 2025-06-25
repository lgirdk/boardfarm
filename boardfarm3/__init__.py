"""Automated testing of network devices."""

__version__ = "2024.12.4a65"

from pluggy import HookimplMarker, HookspecMarker

PROJECT_NAME = "boardfarm"

hookspec = HookspecMarker(PROJECT_NAME)
hookimpl = HookimplMarker(PROJECT_NAME)


__all__ = ["hookimpl", "hookspec"]
