"""Hookspecs contributed by the boardfarm API runtime agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from boardfarm3 import hookspec

if TYPE_CHECKING:
    from argparse import Namespace

    from fastapi import APIRouter
    from pluggy import PluginManager

    from boardfarm3.lib.boardfarm_config import BoardfarmConfig

# pylint: disable=unused-argument


@hookspec(firstresult=True)
def boardfarm_api_resolve_config(
    payload: dict[str, Any],
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
) -> BoardfarmConfig:
    """Turn an opaque session payload into a BoardfarmConfig.

    The control plane never inspects the payload. A plugin may register this
    hook with ``tryfirst`` to accept a front-end specific configuration format.

    :param payload: opaque session payload as posted to the agent
    :type payload: dict[str, Any]
    :param cmdline_args: synthesised boardfarm command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :return: parsed boardfarm config
    :rtype: BoardfarmConfig
    """


@hookspec
def boardfarm_add_api_routers() -> list[APIRouter]:
    """Return FastAPI routers to mount on the runtime agent.

    :return: routers contributed by this plugin
    :rtype: list[APIRouter]
    """
