"""One plugin that cannot be imported must cost only its own routes.

pluggy's ``load_setuptools_entrypoints`` stops at the first entry point whose
import raises, so every plugin listed after it was silently lost -- and in the
agent's runtime the exception escaped and the agent never started.
"""

from __future__ import annotations

import importlib.metadata
from typing import ClassVar

import pytest

GROUP = "boardfarm_api"


class _RecordingEntryPoint(importlib.metadata.EntryPoint):
    """An entry point that records being loaded and then fails to import."""

    loaded: ClassVar[list[str]] = []

    def load(self) -> object:
        type(self).loaded.append(self.name)
        msg = f"cannot import name 'IPAddresses' (plugin {self.name})"
        raise ImportError(msg)


class _FakeDist:
    """Just enough of ``importlib.metadata.Distribution`` for plugin loading."""

    def __init__(self, *entry_points: importlib.metadata.EntryPoint) -> None:
        self.entry_points = list(entry_points)
        self.metadata = {"name": "fake-dist", "version": "0"}


@pytest.fixture(name="installed")
def installed_fixture(monkeypatch: pytest.MonkeyPatch) -> object:
    """Install a broken plugin ahead of a working one.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :return: None
    :rtype: object
    """
    _RecordingEntryPoint.loaded = []
    broken = _RecordingEntryPoint("broken_api", "nowhere:nothing", GROUP)
    good = importlib.metadata.EntryPoint(
        "good_api", "unittests.api._api_plugin_fixture", GROUP
    )
    monkeypatch.setattr(
        importlib.metadata, "distributions", lambda: [_FakeDist(broken, good)]
    )
    monkeypatch.delenv("BOARDFARM_API_DISABLED_PLUGINS", raising=False)
    return None


@pytest.mark.usefixtures("installed")
def test_agent_keeps_the_routes_of_plugins_that_did_import() -> None:
    from fastapi import FastAPI

    from boardfarm3.api.routers import load_plugin_routers

    routers, _ = load_plugin_routers()
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    assert "/good/hello" in app.openapi()["paths"]


@pytest.mark.usefixtures("installed")
def test_control_keeps_the_routes_of_plugins_that_did_import() -> None:
    from boardfarm3_control.openapi import load_plugin_routers

    paths = {route.path for router in load_plugin_routers() for route in router.routes}
    assert "/good/hello" in paths


@pytest.mark.usefixtures("installed")
def test_agent_runtime_starts_despite_a_broken_plugin() -> None:
    from boardfarm3.api.runtime import RuntimeContext, RuntimeOptions

    runtime = RuntimeContext(RuntimeOptions(board_name="board"))
    assert runtime.plugin_manager.get_plugin("good_api") is not None


@pytest.mark.usefixtures("installed")
def test_a_disabled_plugin_is_never_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deny-list must fence a plugin whose import is what is broken."""
    from boardfarm3.api.routers import load_plugin_routers
    from boardfarm3.api.runtime import RuntimeContext, RuntimeOptions
    from boardfarm3_control.openapi import load_plugin_routers as control_load

    monkeypatch.setenv("BOARDFARM_API_DISABLED_PLUGINS", "broken_api")
    load_plugin_routers()
    control_load()
    RuntimeContext(RuntimeOptions(board_name="board"))
    assert _RecordingEntryPoint.loaded == []
