"""The launcher package keeps every import path callers use today."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("name", "module"),
    [
        ("Launcher", "boardfarm3_control.launcher.protocol"),
        ("FakeLauncher", "boardfarm3_control.launcher.fake"),
        ("ProcessLauncher", "boardfarm3_control.launcher.process"),
        ("DockerLauncher", "boardfarm3_control.launcher.docker"),
    ],
)
def test_names_are_reexported_from_their_submodule(name: str, module: str) -> None:
    package = importlib.import_module("boardfarm3_control.launcher")
    submodule = importlib.import_module(module)
    assert getattr(package, name) is getattr(submodule, name)
