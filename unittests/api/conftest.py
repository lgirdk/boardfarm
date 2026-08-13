"""Shared fixtures for boardfarm API unit tests."""

import json
from pathlib import Path
from typing import Any

import pytest

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
