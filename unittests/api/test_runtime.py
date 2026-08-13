"""Unit tests for the boardfarm API runtime context."""

from typing import Any

import pytest

from boardfarm3.api.runtime import RuntimeContext, RuntimeOptions
from boardfarm3.exceptions import EnvConfigError
from boardfarm3.lib.boardfarm_config import BoardfarmConfig


def test_cmdline_args_carry_every_field_devices_read() -> None:
    """Devices read these attributes off cmdline_args; all must be present."""
    context = RuntimeContext(
        RuntimeOptions(board_name="prplos-docker-1", legacy=True, skip_boot=True),
    )
    args = context.cmdline_args
    assert args.board_name == "prplos-docker-1"
    assert args.legacy is True
    assert args.skip_boot is True
    assert args.skip_contingency_checks is False
    assert args.save_console_logs == ""
    assert args.ignore_devices == ""
    assert args.inventory_config == ""
    assert args.env_config == ""


def test_refresh_cmdline_args_picks_up_option_changes() -> None:
    """Options applied after construction must reach cmdline_args."""
    context = RuntimeContext(RuntimeOptions(board_name="prplos-docker-1"))
    assert context.cmdline_args.legacy is False
    context.options.legacy = True
    context.options.save_console_logs = "/var/log/bf"
    context.refresh_cmdline_args()
    assert context.cmdline_args.legacy is True
    assert context.cmdline_args.save_console_logs == "/var/log/bf"


def test_resolve_produces_boardfarm_config(native_payload: dict[str, Any]) -> None:
    """Resolving a native payload yields a BoardfarmConfig.

    :param native_payload: native session payload
    :type native_payload: dict[str, Any]
    """
    context = RuntimeContext(RuntimeOptions(board_name="prplos-docker-1"))
    config = context.resolve(native_payload)
    assert isinstance(config, BoardfarmConfig)
    assert context.config is config


def test_resolve_unknown_board_raises(native_payload: dict[str, Any]) -> None:
    """An unknown board name surfaces as EnvConfigError.

    :param native_payload: native session payload
    :type native_payload: dict[str, Any]
    """
    context = RuntimeContext(RuntimeOptions(board_name="does-not-exist"))
    with pytest.raises(EnvConfigError):
        context.resolve(native_payload)


def test_register_devices_registers_every_inventory_device(
    native_payload: dict[str, Any],
) -> None:
    """Every device in the resolved inventory becomes a registered plugin.

    :param native_payload: native session payload
    :type native_payload: dict[str, Any]
    """
    context = RuntimeContext(RuntimeOptions(board_name="prplos-docker-1"))
    context.resolve(native_payload)
    device_manager = context.register_devices()
    registered = {name for name, _ in context.plugin_manager.list_name_plugin()}
    assert {"board", "lan", "wan"} <= registered
    assert context.device_manager is device_manager


def test_ignore_devices_skips_named_devices(native_payload: dict[str, Any]) -> None:
    """Devices listed in ignore_devices are not registered.

    :param native_payload: native session payload
    :type native_payload: dict[str, Any]
    """
    context = RuntimeContext(
        RuntimeOptions(board_name="prplos-docker-1", ignore_devices="lan"),
    )
    context.resolve(native_payload)
    context.register_devices()
    registered = {name for name, _ in context.plugin_manager.list_name_plugin()}
    assert "lan" not in registered
    assert "wan" in registered
