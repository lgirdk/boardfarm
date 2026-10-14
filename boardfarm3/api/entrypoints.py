"""Plugin entry-point loading that isolates each plugin from the others."""

from __future__ import annotations

import importlib.metadata
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pluggy

DISABLED_PLUGINS_ENV = "BOARDFARM_API_DISABLED_PLUGINS"

_log = logging.getLogger(__name__)


def disabled_plugins() -> frozenset[str]:
    """Return the ``boardfarm_api`` entry-point names to leave unloaded.

    Read from ``BOARDFARM_API_DISABLED_PLUGINS`` as a comma-separated list.
    Unset or empty disables nothing.

    :return: entry-point names to skip
    :rtype: frozenset[str]
    """
    raw = os.environ.get(DISABLED_PLUGINS_ENV, "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def load_entrypoints(
    plugin_manager: pluggy.PluginManager,
    group: str,
    *,
    skip: frozenset[str] = frozenset(),
) -> list[str]:
    """Register every entry point of *group*, one plugin at a time.

    Unlike ``PluginManager.load_setuptools_entrypoints``, a plugin that raises
    on import is logged and skipped instead of aborting every entry point
    after it, and a name in *skip* is never imported at all -- which is what
    lets the deny-list fence a plugin whose import is what is broken.

    :param plugin_manager: manager to register the plugins on
    :type plugin_manager: pluggy.PluginManager
    :param group: entry-point group, e.g. ``boardfarm_api``
    :type group: str
    :param skip: entry-point names not to import
    :type skip: frozenset[str]
    :return: names of the plugins that failed to import
    :rtype: list[str]
    """
    failed: list[str] = []
    for dist in list(importlib.metadata.distributions()):
        for entry_point in dist.entry_points:
            name = entry_point.name
            if entry_point.group != group:
                continue
            if name in skip:
                _log.info("%s plugin %r disabled by environment", group, name)
                continue
            if plugin_manager.get_plugin(name) or plugin_manager.is_blocked(name):
                continue
            try:
                plugin = entry_point.load()
            except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                _log.exception(
                    "%s plugin %r could not be imported; skipped", group, name
                )
                failed.append(name)
                continue
            plugin_manager.register(plugin, name=name)
    return failed


_PLUGIN_GROUPS = ("boardfarm", "boardfarm_api")


def plugin_versions() -> dict[str, str]:
    """Return the version of boardfarm3 and of every installed boardfarm plugin.

    Control and agent each compute this; a difference means they would not
    agree on which routes exist.

    :return: distribution name to version
    :rtype: dict[str, str]
    """
    from boardfarm3 import __version__  # noqa: PLC0415

    versions: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        if any(ep.group in _PLUGIN_GROUPS for ep in dist.entry_points):
            versions[dist.metadata["Name"]] = dist.version
    versions["boardfarm3"] = __version__
    return versions
