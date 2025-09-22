"""Boardfarm environment config module."""

import json
import logging
from copy import deepcopy
from functools import cached_property
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
        """Environment config dictionary.

        :returns: env config response
        """
        return self._env_config

    @property
    def inventory_config(self) -> dict[str, Any]:
        """Inventory config dictionary.

        :returns: inventory config response
        """
        return self._inventory_config

    @cached_property
    def resource_name(self) -> str:
        """Resource name.

        :returns: resource name of the board
        """
        conf = self.get_device_config("board")
        return conf["resource_name"]

    def get_board_station_number(self) -> int:
        """Get station number of the board.

        :returns: station number
        """
        return int(self.resource_name.split("-")[-1])

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
        msg = f"{device_name} - Unknown device name"
        raise EnvConfigError(msg)

    def get_board_sku(self) -> str:
        """Return the env config ["environment_def"]["board"]["SKU"] value.

        :return: SKU value
        :raises EnvConfigError: when given sku is unknown
        """
        try:
            return self.env_config["environment_def"]["board"]["SKU"]
        except (KeyError, AttributeError) as e:
            msg = "Board SKU is not found in env config."
            raise EnvConfigError(msg) from e

    def get_board_model(self) -> str:
        """Return the env config ["environment_def"]["board"]["model"].

        :return: Board model
        :raises EnvConfigError: when given model is unknown
        """
        try:
            return self.env_config["environment_def"]["board"]["model"]
        except (KeyError, AttributeError) as e:
            msg = "Unable to find board.model entry in env config."
            raise EnvConfigError(
                msg,
            ) from e

    def get_prov_mode(self) -> str:
        """Return the provisioning mode of the DUT.

        :return: ipv4, ipv6, dslite, dualstack, disabled
        :raises EnvConfigError: when given sku is unknown
        """
        try:
            return self.env_config["environment_def"]["board"][
                "eRouter_Provisioning_mode"
            ]
        except (KeyError, AttributeError) as e:
            msg = "Unable to find eRouter_Provisioning_mode entry in env config."
            raise EnvConfigError(
                msg,
            ) from e


def _merge_with_wifi_config(
    wifi_devices: list[dict[str, Any]],
    env_json_config: dict[str, Any],
) -> list[dict[str, Any]]:
    wifi_clients: list[dict[str, Any]] = get_value_from_dict(
        "wifi_clients",
        env_json_config,
    )
    if wifi_clients is None:
        return []
    if len(wifi_devices) < len(wifi_clients):
        msg = (
            f"Inventory config doesn't have {len(wifi_clients)} "
            "Wi-Fi clients requested by env config"
        )
        raise EnvConfigError(
            msg,
        )
    merged_wifi_devices: list[dict[str, Any]] = []
    wifi_devices_copy = deepcopy(wifi_devices)
    wifi_clients = sorted(wifi_clients, key=lambda x: x.get("band"))
    wifi_devices_copy = sorted(wifi_devices_copy, key=lambda x: x.get("band"))
    for wifi_client in wifi_clients:
        found = None
        for wifi_device in wifi_devices_copy:
            if wifi_device.get("band") in {wifi_client.get("band"), "dual"}:
                merged_wifi_devices.append(wifi_device.copy() | wifi_client.copy())
                found = wifi_device
                break
        else:
            msg = (
                f"Unable to find a wifi device for {wifi_client} "
                "env config Wi-Fi client in inventory config"
            )
            raise EnvConfigError(msg)
        if found:
            wifi_devices_copy.remove(found)
    return merged_wifi_devices


def _merge_with_lan_config(
    lan_devices: list[dict[str, Any]],
    env_json_config: dict[str, Any],
) -> list[dict[str, Any]]:
    lan_clients: list[dict[str, str]] = get_value_from_dict(
        "lan_clients",
        env_json_config,
    )
    if lan_clients is None:
        return []
    if len(lan_devices) < len(lan_clients):
        msg = (
            f"Inventory config doesn't have {len(lan_clients)} "
            "LAN clients requested by env config"
        )
        raise EnvConfigError(
            msg,
        )
    return [
        lan_devices[index] | lan_client for index, lan_client in enumerate(lan_clients)
    ]


def get_json(resource_name: str) -> dict[str, Any]:
    """Get the inventory json either from a URL or a system path.

    :param resource_name: inventory resource name
    :type resource_name: str
    :return: the inventory json from the specified path
    :rtype: dict[str, Any]
    """
    if resource_name.startswith(("http://", "https://")):
        json_dict = requests.get(resource_name, timeout=30).text
    else:
        json_dict = Path(resource_name).read_text(encoding="utf-8")
    return cast("dict[str, Any]", json.loads(json_dict))


def get_inventory_config(
    resource_name: str,
    inventory_json_path: str,
) -> dict[str, Any]:
    """Return inventory config based on given arguments.

    :param resource_name: inventory resource name
    :type resource_name: str
    :param inventory_json_path: inventory json config path
    :type inventory_json_path: str
    :raises EnvConfigError: on resource name not found in inventory config
    :raises EnvConfigError: on invalid location config
    :return: inventory configuration
    :rtype: dict[str, Any]
    """
    full_inventory_config = get_json(inventory_json_path)
    if resource_name not in full_inventory_config:
        msg = f"{resource_name!r} resource not found in inventory config"
        raise EnvConfigError(
            msg,
        )
    inventory_config = full_inventory_config.get(resource_name)
    if "location" in inventory_config:
        if locations := full_inventory_config.get(
            "locations",
            {},
        ):  # optional, lab dependent
            inventory_config["devices"] += locations[
                inventory_config.pop("location")
            ].get("devices", [])
        else:
            msg = f"{inventory_config['location']!r} invalid location config"
            raise EnvConfigError(msg)
    for device in inventory_config.get("devices", []):
        if device["name"] == "board":
            device["resource_name"] = resource_name
            break
    return inventory_config


def parse_boardfarm_config(
    inventory_config: dict[str, Any],
    env_json_config: dict[str, Any],
) -> BoardfarmConfig:
    """Get environment config from given json files.

    :param inventory_config: inventory config
    :type inventory_config: dict[str, Any]
    :param env_json_config: environment config
    :type env_json_config: dict[str, Any]
    :return: boardfarm config instance
    :rtype: BoardfarmConfig
    """
    # disable jsonmerge debug logs
    logging.getLogger("jsonmerge").setLevel(logging.WARNING)
    wifi_devices = [
        device
        for device in inventory_config["devices"]
        if device["type"] in ["bf_wlan", "debian_wifi"]
    ]
    lan_devices = [
        device
        for device in inventory_config["devices"]
        if device["type"] in ["bf_lan", "debian_lan"]
    ]
    other_devices = [
        device
        for device in inventory_config["devices"]
        if device not in wifi_devices + lan_devices
    ]
    merged_devices_config = []
    environment_def = env_json_config.get("environment_def")
    for device in other_devices:
        device_name = device.get("name")
        merged_devices_config.append(
            (
                jsonmerge.merge(device, environment_def[device_name])
                if device_name in environment_def
                else device
            ),
        )
    merged_devices_config += _merge_with_lan_config(lan_devices, env_json_config)
    merged_devices_config += _merge_with_wifi_config(wifi_devices, env_json_config)
    return BoardfarmConfig(merged_devices_config, env_json_config, inventory_config)
