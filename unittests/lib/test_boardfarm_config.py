"""Unit tests for the Boardfarm environment config module."""

import copy
import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
import requests
from pytest_mock import MockerFixture

from boardfarm3.exceptions import EnvConfigError
from boardfarm3.lib.boardfarm_config import (
    BoardfarmConfig,
    get_inventory_config,
    get_json,
    parse_boardfarm_config,
)

_TEST_DATA_PATH = Path(__file__).parent.parent / "testdata"

_VALID_ENV_CONFIG_PATH = str(_TEST_DATA_PATH / "env_conf.json")

_VALID_INVENTORY_CONFIG_PATH = str(_TEST_DATA_PATH / "inventory_conf.json")

_ENV_CONFIG_WITH_WIFI_CLIENTS_PATH = str(
    _TEST_DATA_PATH / "env_conf_with_wifi_clients.json",
)

_VALID_INVENTORY_CONFIG = get_json(_VALID_INVENTORY_CONFIG_PATH)

_VALID_ENV_CONFIG = get_json(_VALID_ENV_CONFIG_PATH)

_INVALID_INVENTORY_CONFIG = get_json(
    str(_TEST_DATA_PATH / "invalid_device_inventory_conf.json"),
)

_MERGED_DEVICE_CONFIG = cast(
    list[dict[Any, Any]],
    get_json(
        str(_TEST_DATA_PATH / "merged_device_config.json"),
    ),
)

_WAN_DEVICE_CONFIG = get_json(str(_TEST_DATA_PATH / "wan_device_config.json"))

_SINGLE_LAN_ENV_CONFIG = get_json(str(_TEST_DATA_PATH / "env_conf_single_lan.json"))

_WIFI_CLIENTS_ENV_CONFIG = get_json(_ENV_CONFIG_WITH_WIFI_CLIENTS_PATH)


class _ResponseStub:
    """HTTP/HTTPS requests response stub."""

    def __init__(self, url: str, content: str, success: bool) -> None:
        self.url = url
        self.content = content
        self._success = success

    @property
    def text(self) -> str:
        return self.content


def test_env_config_valid_env_config() -> None:
    """Verifies whether the provided environment configuration is valid."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _VALID_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )

    assert bf_config.env_config == _VALID_ENV_CONFIG


def test_env_config_valid_inventory_config() -> None:
    """Verifies whether the provided inventory configuration is valid."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _VALID_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )

    assert bf_config.inventory_config == _VALID_INVENTORY_CONFIG


def test_get_devices_config_valid_configs() -> None:
    """Examines whether valid inventory and environment configurations are successfully combined into a single config."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _VALID_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )
    assert bf_config.get_devices_config() == _MERGED_DEVICE_CONFIG


def test_get_device_config_valid_device_name() -> None:
    """Checks whether a device configuration can be obtained from the merged configuration if it exists."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _VALID_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )

    assert bf_config.get_device_config("wan") == _WAN_DEVICE_CONFIG


def test_get_device_config_invalid_device() -> None:
    """Ensure that an error is raised when attempting to retrieve the configuration of an invalid or non-existent device."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _VALID_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )
    with pytest.raises(EnvConfigError, match="XXX - Unknown device name"):
        bf_config.get_device_config("XXX")


def test_get_board_sku_value_available_in_env_conf() -> None:
    """Ensure that the board SKU value can be extracted from the configuration if it is present."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _VALID_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )
    assert bf_config.get_board_sku() == "Ziggo"


def test_get_board_sku_value_not_available_in_env_conf() -> None:
    """Ensure that an error is raised when attempting to retrieve the board SKU value from device configurations when it is not present."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _SINGLE_LAN_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )
    with pytest.raises(EnvConfigError, match="Board SKU is not found in env config."):
        bf_config.get_board_sku()


def test_get_board_model_value_available_in_env_conf() -> None:
    """Ensure that the board model value can be extracted from the configuration if it is present."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _VALID_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )
    assert bf_config.get_board_model() == "CH7465LG"


def test_get_board_model_value_not_available_in_env_conf() -> None:
    """Ensure that an error is raised when attempting to retrieve the board model value from device configurations when it is not present."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _SINGLE_LAN_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )
    with pytest.raises(
        EnvConfigError,
        match="Unable to find board.model entry in env config.",
    ):
        bf_config.get_board_model()


def test_get_prov_mode_value_available_in_env_conf() -> None:
    """Ensure that the board prov mode value can be extracted from the configuration if it is present."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _VALID_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )
    assert bf_config.get_prov_mode() == "dual"


def test_get_prov_mode_value_not_available_in_env_conf() -> None:
    """Ensure that an error is raised when attempting to retrieve the prov mode value from device configurations when it is not present."""
    bf_config = BoardfarmConfig(
        _MERGED_DEVICE_CONFIG,
        _SINGLE_LAN_ENV_CONFIG,
        _VALID_INVENTORY_CONFIG,
    )
    with pytest.raises(
        EnvConfigError,
        match="Unable to find eRouter_Provisioning_mode entry in env config.",
    ):
        bf_config.get_prov_mode()


def test_get_json_valid_env_path() -> None:
    """Confirm that a JSON file can be obtained from a provided valid file path."""
    assert get_json(_VALID_ENV_CONFIG_PATH) == _VALID_ENV_CONFIG


def test_get_json_file_valid_https_request(mocker: MockerFixture) -> None:
    """Confirm that a JSON file can be retrieved through an HTTPS request..

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    """
    mocker.patch.object(
        requests,
        attribute="get",
        return_value=_ResponseStub(
            "https://valid.device-env.com",
            json.dumps(_VALID_ENV_CONFIG),
            success=True,
        ),
    )
    assert get_json("https://valid.device-env.com") == _VALID_ENV_CONFIG


def test_get_json_file_valid_http_request(mocker: MockerFixture) -> None:
    """Confirm that a JSON file can be retrieved through an HTTP request..

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    """
    mocker.patch.object(
        requests,
        attribute="get",
        return_value=_ResponseStub(
            "http://valid.device-env.com",
            json.dumps(_VALID_ENV_CONFIG),
            success=True,
        ),
    )
    assert get_json("http://valid.device-env.com") == _VALID_ENV_CONFIG


def test_get_json_file_invalid_response(mocker: MockerFixture) -> None:
    """Ensure that a JSONDecodeError is raised when an invalid HTTP request is provided..

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    """
    mocker.patch.object(
        requests,
        attribute="get",
        return_value=_ResponseStub(
            "http://invalid.device-env.com",
            "Invalid Response",
            success=True,
        ),
    )
    with pytest.raises(
        json.JSONDecodeError,
        match=re.escape("Expecting value: line 1 column 1 (char 0)"),
    ):
        get_json("http://invalid.device-env.com")


def test_get_inventory_config_valid_inventory_config() -> None:
    """Verify that inventory config for a device is retrieved if the device exists in inventory config passed."""
    del _VALID_INVENTORY_CONFIG["CH7465LG-2-2"]["location"]
    assert (
        get_inventory_config(
            "CH7465LG-2-2",
            _VALID_INVENTORY_CONFIG_PATH,
        ).keys()
        == _VALID_INVENTORY_CONFIG["CH7465LG-2-2"].keys()
    )


def test_get_inventory_config_resource_not_found() -> None:
    """Ensure that an "EnvConfigError" is raised when attempting to retrieve an invalid device from the inventory configuration."""
    with pytest.raises(
        EnvConfigError,
        match="'DEVICE-XXX' resource not found in inventory config",
    ):
        get_inventory_config(
            "DEVICE-XXX",
            _VALID_INVENTORY_CONFIG_PATH,
        )


def test_get_inventory_config_invalid_location_config() -> None:
    """Ensure that an "EnvConfigError" is triggered when attempting to retrieve a device's inventory configuration with invalid location details."""
    with pytest.raises(
        EnvConfigError,
        match="'ams-cmts5-md1' invalid location config",
    ):
        get_inventory_config(
            "XXXX",
            str(_TEST_DATA_PATH / "invalid_device_inventory_conf.json"),
        )


def test_parse_boardfarm_config_valid_inventory_env_configs() -> None:
    """Ensure that the parsing of device configuration is successful when valid inventory and environment configurations are provided."""
    bf_config = parse_boardfarm_config(
        inventory_config=_VALID_INVENTORY_CONFIG["CH7465LG-2-2"],
        env_json_path=_VALID_ENV_CONFIG_PATH,
    )
    assert bf_config.env_config == _VALID_ENV_CONFIG
    assert bf_config._merged_devices_config == _MERGED_DEVICE_CONFIG
    assert _VALID_INVENTORY_CONFIG["CH7465LG-2-2"] == bf_config.inventory_config


def test_parse_boardfarm_config_env_inventory_requirement_missmatch() -> None:
    """Ensure that an "EnvConfigError" is raised during the parsing of device configuration when an invalid inventory configuration and a valid environment configuration are provided."""
    with pytest.raises(EnvConfigError):
        parse_boardfarm_config(
            inventory_config=_INVALID_INVENTORY_CONFIG["XXXX"],
            env_json_path=_VALID_ENV_CONFIG_PATH,
        )


def test_parse_boardfarm_config_no_sufficient_lan_clients() -> None:
    """Ensure that an "EnvConfigError" is raised during the parsing of device configuration when there is a LAN clients count mismatch between the inventory and environment configurations."""
    with pytest.raises(EnvConfigError):
        parse_boardfarm_config(
            inventory_config=_INVALID_INVENTORY_CONFIG["XXXX"],
            env_json_path=str(_TEST_DATA_PATH / "env_conf_single_lan.json"),
        )


def test_parse_boardfarm_config_no_lan_clients() -> None:
    """Ensure that the parsing of device configuration is successful when both an inventory configuration and an environment configuration are provided, and neither of them specifies LAN clients."""
    bf_config = parse_boardfarm_config(
        inventory_config=_INVALID_INVENTORY_CONFIG["XXXX"],
        env_json_path=str(_TEST_DATA_PATH / "env_conf_no_lans.json"),
    )
    assert bf_config._merged_devices_config[0]["lan_clients"] is None


def test_parse_boardfarm_config_wifi_clients_available() -> None:
    """Ensure that the parsing of device configuration is successful when both an inventory configuration and an environment configuration are provided with wi-fi clients."""
    bf_config = parse_boardfarm_config(
        inventory_config=_VALID_INVENTORY_CONFIG["CH7465LG-2-2"],
        env_json_path=_ENV_CONFIG_WITH_WIFI_CLIENTS_PATH,
    )
    assert (
        bf_config._merged_devices_config[0]["wifi_clients"]
        == _WIFI_CLIENTS_ENV_CONFIG["environment_def"]["board"]["wifi_clients"]
    )


def test_parse_boardfarm_config_requested_wifi_clients_not_available() -> None:
    """Ensure that an "EnvConfigError" is raised during the parsing of device configuration when there is a WI-FI clients count mismatch between the inventory and environment configurations."""
    with pytest.raises(
        EnvConfigError,
        match="Inventory config doesn't have 3 Wi-Fi clients requested by env config",
    ):
        parse_boardfarm_config(
            inventory_config=_INVALID_INVENTORY_CONFIG["XXXX"],
            env_json_path=_ENV_CONFIG_WITH_WIFI_CLIENTS_PATH,
        )


def test_parse_boardfarm_config_wifi_device_not_found_for_band_env_wifi_client() -> (
    None
):
    """Ensure that an "EnvConfigError" is raised during the parsing of device configuration when there is a WI-FI clients type mismatch between the inventory and environment configurations."""
    inventory_config_copy = copy.deepcopy(_VALID_INVENTORY_CONFIG)
    for device in inventory_config_copy["CH7465LG-2-2"]["devices"]:
        if "band" in device:
            device["band"] = ""
            break
    err_msg = "Unable to find a wifi device for (.*) env config Wi-Fi client in inventory config"
    with pytest.raises(
        EnvConfigError,
        match=err_msg,
    ):
        parse_boardfarm_config(
            inventory_config=inventory_config_copy["CH7465LG-2-2"],
            env_json_path=_ENV_CONFIG_WITH_WIFI_CLIENTS_PATH,
        )


def test_parse_boardfarm_config_wan_clients_available() -> None:
    """Ensure that the parsing of device configuration is successful when both an inventory configuration and an environment configuration are provided with WAN clients."""
    bf_config = parse_boardfarm_config(
        inventory_config=_VALID_INVENTORY_CONFIG["CH7465LG-2-2"],
        env_json_path=_VALID_ENV_CONFIG_PATH,
    )
    assert (
        bf_config._merged_devices_config[0]["wan_clients"]
        == _VALID_ENV_CONFIG["environment_def"]["board"]["wan_clients"]
    )
