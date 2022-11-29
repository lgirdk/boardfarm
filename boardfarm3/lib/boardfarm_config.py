"""Boardfarm environment config module."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from nested_lookup import nested_lookup

from boardfarm3.exceptions import EnvConfigError


class BoardfarmConfig:
    """Boardfarm environment config."""

    _merged_devices_config: list[dict]

    def __init__(
        self,
        merged_config: list[dict],
        env_config: dict[str, Any],
        inventory_config: dict[str, Any],
    ):
        """Initialize boardfarm config.

        :param merged_config: merged devices config
        :param env_config: environment configuration
        :param inventory_config: inventory configuration
        """
        self._env_config = env_config
        self._inventory_config = inventory_config
        self._merged_devices_config = merged_config

    @property
    def env_config(self) -> dict[str, Any]:
        """Environment config dictionary."""
        return self._env_config

    @property
    def inventory_config(self) -> dict[str, Any]:
        """Inventory config dictionary."""
        return self._inventory_config

    def get_devices_config(self) -> list[dict]:
        """Get merged devices config.

        :returns: merged devices config
        """
        return self._merged_devices_config

    def get_device_config(self, device_name: str) -> dict[str, Any]:
        """Get device merged config.

        :param device_name: device name
        :returns: merged device config
        :raises EnvConfigError: when given device name is unknown
        """
        for device_config in self._merged_devices_config:
            if device_config.get("name") == device_name:
                return device_config
        raise EnvConfigError(f"{device_name} - Unknown device name")

    def get_board_sku(self) -> str:
        """Return the env config ["environment_def"]["board"]["SKU"] value.

        :return: SKU value
        """
        try:
            return self.env_config["environment_def"]["board"]["SKU"]
        except (KeyError, AttributeError) as e:
            raise EnvConfigError("Board SKU is not found in env config.") from e

    def get_board_model(self) -> str:
        """Return the env config ["environment_def"]["board"]["model"].

        :return: Board model
        """
        try:
            return self.env_config["environment_def"]["board"]["model"]
        except (KeyError, AttributeError) as e:
            raise EnvConfigError(
                "Unable to find board.model entry in env config."
            ) from e

    def get_prov_mode(self) -> str:
        """Return the provisioning mode of the DUT.

        Possible values: ipv4, ipv6, dslite, dualstack, disabled
        """
        try:
            return self.env_config["environment_def"]["board"][
                "eRouter_Provisioning_mode"
            ]
        except (KeyError, AttributeError) as e:
            raise EnvConfigError(
                "Unable to find eRouter_Provisioning_mode entry in env config."
            ) from e


def _merge_with_wifi_config(device: Any, wifi_config: Any) -> Any:
    if device.get("type") == "debian_wifi" and wifi_config:
        w_config = wifi_config
        for wifi in w_config:
            if device["band"] in [wifi["band"], "dual"]:
                wifi_config.remove(wifi)
                return wifi, wifi_config
    return {}, wifi_config


def parse_boardfarm_config(
    resource_name: str, env_json_path: str, inventory_json_path: str
) -> BoardfarmConfig:
    """Get environment config from given json files.

    :param resource_name: inventory resource name
    :param env_json_path: environment json file path
    :param inventory_json_path: inventory json file path
    :returns: environment configuration instance
    """
    # TODO: this code needs revisiting as it the configuration inflexible
    # and makes assumtions that may not be applicable
    env_json_config = json.loads(Path(env_json_path).read_text(encoding="utf-8"))
    inventory_config = json.loads(Path(inventory_json_path).read_text(encoding="utf-8"))
    env_json_config_copy = deepcopy(env_json_config)
    inventory_config_copy = deepcopy(inventory_config)
    board_config = inventory_config.get(resource_name)
    env_devices = board_config.pop("devices")
    board_config["type"] = board_config.pop("board_type")
    location_config = {}
    if inventory_config.get("locations", {}):  # optional, lab dependent
        location_config = inventory_config["locations"].get(
            board_config.pop("location")
        )
        board_config["mirror"] = location_config.get("mirror", None)  # optional
        env_devices.extend(location_config.get("devices", []))
    env_devices.append(board_config)
    environment_def = env_json_config.get("environment_def")
    wifi_config: list = nested_lookup("wifi_clients", env_json_config)
    wifi_config = wifi_config[-1] if wifi_config else []
    merged_devices_config = []
    for device in env_devices:
        if device.get("name") in environment_def:
            device = environment_def[device.get("name")] | device
        wifi, wifi_config = _merge_with_wifi_config(device, wifi_config)
        merged_devices_config.append(device | wifi)
    return BoardfarmConfig(
        merged_devices_config, env_json_config_copy, inventory_config_copy
    )
