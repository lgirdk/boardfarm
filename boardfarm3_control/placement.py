"""Which lab host a board's agent runs on."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from boardfarm3_control.errors import NoHostForBoard, UnknownHost

if TYPE_CHECKING:
    from boardfarm3_control.hosts import HostRegistry


def resolve_host(payload: dict[str, Any], board_name: str, hosts: HostRegistry) -> str:
    """Pick the host from ``payload.inventory[board_name].agent_host``, else the default.

    :param payload: the session-create payload (``inventory`` and ``env``)
    :type payload: dict[str, Any]
    :param board_name: the board being leased
    :type board_name: str
    :param hosts: the host registry
    :type hosts: HostRegistry
    :return: the host name
    :rtype: str
    :raises NoHostForBoard: when neither the inventory nor a default names a host
    :raises UnknownHost: when ``agent_host`` is not a known host name
    """
    inventory = payload.get("inventory")
    entry = inventory.get(board_name) if isinstance(inventory, dict) else None
    requested = entry.get("agent_host") if isinstance(entry, dict) else None
    if requested is None:
        default = hosts.default_host()
        if default is None:
            msg = f"inventory names no agent_host for board {board_name} and no default host is set"
            raise NoHostForBoard(msg, board_name=board_name)
        return default
    if not isinstance(requested, str) or requested not in hosts.names():
        msg = f"agent_host {requested!r} for board {board_name} is not a known host"
        raise UnknownHost(msg, board_name=board_name, host=requested)
    return requested
