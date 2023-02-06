"""Boardfarm environment config module."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import jsonmerge
import requests

from boardfarm3.exceptions import EnvConfigError
from boardfarm3.lib.utils import get_value_from_dict


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


def _merge_with_wifi_config(
    wifi_devices: list[dict[str, Any]], env_json_config: dict[str, Any]
) -> list[dict[str, Any]]:
    wifi_clients: list[dict[str, Any]] = get_value_from_dict(
        "wifi_clients", env_json_config
    )
    if wifi_clients is None:
        return []
    if len(wifi_devices) < len(wifi_clients):
        raise EnvConfigError(
            f"Inventory config doesn't have {len(wifi_clients)} wifi clients"
            " requested by env config"
        )
    merged_wifi_devices: list[dict[str, Any]] = []
    wifi_devices_copy = deepcopy(wifi_devices)
    wifi_clients = sorted(wifi_clients, key=lambda x: x.get("band"))
    wifi_devices_copy = sorted(wifi_devices_copy, key=lambda x: x.get("band"))
    for wifi_client in wifi_clients:
        for wifi_device in wifi_devices_copy:
            if wifi_device.get("band") in {wifi_client.get("band"), "dual"}:
                merged_wifi_devices.append(wifi_device | wifi_client)
                wifi_devices_copy.remove(wifi_device)
                break
        else:
            raise EnvConfigError(
                f"Unable to find a wifi device for {wifi_client}"
                " env config wifi client in inventory config"
            )
    return merged_wifi_devices


def _merge_with_lan_config(
    lan_devices: list[dict[str, Any]], env_json_config: dict[str, Any]
) -> list[dict[str, Any]]:
    lan_clients: list[dict[str, str]] = get_value_from_dict(
        "lan_clients", env_json_config
    )
    if lan_clients is None:
        return []
    if len(lan_devices) < len(lan_clients):
        raise EnvConfigError(
            f"Inventory config doesn't have {len(lan_clients)} lan clients"
            " requested by env config"
        )
    return [
        lan_devices[index] | lan_client for index, lan_client in enumerate(lan_clients)
    ]


def _get_json(resource_name: str) -> dict[str, Any]:
    json_dict: str
    if resource_name.startswith(("http://", "https://")):
        json_dict = requests.get(resource_name, timeout=30).text
    else:
        json_dict = Path(resource_name).read_text(encoding="utf-8")
    return cast(dict[str, Any], json.loads(json_dict))


def parse_boardfarm_config(  # pylint: disable=too-many-locals
    resource_name: str, env_json_path: str, inventory_json_path: str
) -> BoardfarmConfig:
    """Get environment config from given json files.

    :param resource_name: inventory resource name
    :param env_json_path: environment json file path
    :param inventory_json_path: inventory json file path
    :returns: environment configuration instance
    """
    env_json_config = _get_json(env_json_path)
    inventory_config = _get_json(inventory_json_path)
    if resource_name not in inventory_config:
        raise EnvConfigError(
            f"{resource_name!r} resource not found in inventory config"
        )
    resource_config = inventory_config.get(resource_name)
    if "location" in resource_config:
        if locations := inventory_config.get(
            "locations", {}
        ):  # optional, lab dependent
            resource_config["devices"] += locations[
                resource_config.pop("location")
            ].get("devices", [])
        else:
            raise EnvConfigError(
                f"{resource_config['location']!r} not found in inventory config"
            )
    wifi_devices = [
        device
        for device in resource_config["devices"]
        if device["type"] == "debian_wifi"
    ]
    lan_devices = [
        device
        for device in resource_config["devices"]
        if device["type"] == "debian_lan"
    ]
    other_devices = [
        device
        for device in resource_config["devices"]
        if device not in wifi_devices + lan_devices
    ]
    merged_devices_config = []
    environment_def = env_json_config.get("environment_def")
    for device in other_devices:
        device_name = device.get("name")
        merged_devices_config.append(
            jsonmerge.merge(device, environment_def[device_name])
            if device_name in environment_def
            else device
        )
    merged_devices_config += _merge_with_lan_config(lan_devices, env_json_config)
    merged_devices_config += _merge_with_wifi_config(wifi_devices, env_json_config)
    return BoardfarmConfig(merged_devices_config, env_json_config, inventory_config)
