"""Shared fixtures for boardfarm API unit tests."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from boardfarm3.api.runtime import RuntimeOptions
from boardfarm3.api.session import Session
from boardfarm3.lib import device_manager as device_manager_module

CONFIGS = Path(__file__).parents[2] / "boardfarm3" / "configs"


@pytest.fixture(autouse=True)
def _reset_device_manager_singleton() -> Any:
    """Clear the DeviceManager process global around every test.

    ``pytest-randomly`` shuffles test order, so a leaked singleton would make
    failures depend on ordering.

    :yield: None
    :rtype: Any
    """
    device_manager_module._DEVICE_MANAGER_INSTANCE = None
    yield
    device_manager_module._DEVICE_MANAGER_INSTANCE = None


@pytest.fixture(name="native_payload")
def native_payload_fixture() -> dict[str, Any]:
    """Load the shipped example inventory and env config as a native payload.

    :return: native session payload
    :rtype: dict[str, Any]
    """
    return {
        "inventory": json.loads(
            (CONFIGS / "boardfarm_config_example.json").read_text(encoding="utf-8"),
        ),
        "env": json.loads(
            (CONFIGS / "boardfarm_env_example.json").read_text(encoding="utf-8"),
        ),
    }


class FakeRuntime:
    """RuntimeContext stand-in that touches no devices."""

    def __init__(self) -> None:
        """Initialise the fake."""
        self.config: object | None = None
        self.device_manager: object | None = None

    def refresh_cmdline_args(self) -> None:
        """Re-materialise options. No-op for the fake."""

    def resolve(self, payload: dict[str, Any]) -> object:  # noqa: ARG002
        """Resolve the payload.

        :param payload: opaque payload
        :type payload: dict[str, Any]
        :return: placeholder config
        :rtype: object
        """
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Register devices.

        :return: placeholder device manager
        :rtype: object
        """
        self.device_manager = object()
        return self.device_manager


@pytest.fixture(name="make_session")
def make_session_fixture() -> Callable[..., Session]:
    """Return a factory building a Session with a device-free runtime.

    :return: factory taking RuntimeOptions keyword overrides
    :rtype: Callable[..., Session]
    """

    def _make(**overrides: Any) -> Session:
        options = RuntimeOptions(board_name="board", **overrides)
        return Session("s-test", options, runtime=FakeRuntime())

    return _make
