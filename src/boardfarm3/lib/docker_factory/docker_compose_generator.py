"""Library to generate docker-compose.yml payload to docker factory v2."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonmerge

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_config import BoardfarmConfig


_DEVICE_MAP = {"EXT_VOIP": "softphone", "SIP": "sipcenter"}


# pylint: disable=too-few-public-methods
class DockerComposeGenerator:
    """Class to manage docker-compose.yml payload for docker factory v2."""

    def __init__(self, boardfarm_config: BoardfarmConfig) -> None:
        """Initialize the YMLManager for Docker Factory v2.

        :param boardfarm_config: Boardfarm Config instance
        :type boardfarm_config: BoardfarmConfig
        """
        self._templates_path = Path(__file__).parent / "templates"
        self._boardfarm_config = boardfarm_config
        self._devices_list: list[str] = []
        self._get_devices(self._boardfarm_config.env_config)

    def _get_device_json_path(self, device_name: str | None = None) -> Path:
        """Return the path of the specified device json template.

        :param device_name: Name of the device whose json template path is to be
            fetched, defaults to None
        :type device_name: Optional[str], optional
        :return: path of the specific device json template if device_name is provided,
            else returns the base factory template
        :rtype: Path
        """
        if device_name:
            return self._templates_path / f"docker-compose.{device_name}.tmpl.json"
        return self._templates_path / "docker-compose.tmpl.json"

    def _update_ports(self, port_mapping: list[str], increment: int) -> list[str]:
        updated_ports = []
        for mapping in port_mapping:
            ports = mapping.split(":")
            host_port = int(ports[0]) + increment
            container_port = ports[1]
            updated_ports.append(f"{host_port}:{container_port}")
        return updated_ports

    def _get_requested_device_count(self, device_name: str) -> int:
        """Get the requested number of devices based on the device name.

        :param device_name: The name of the device
        :type device_name: str
        :return: The requested device count to be deployed
        :rtype: int
        """

        def recursive_count(data: list | dict | int) -> int:
            if isinstance(data, list):
                return sum(recursive_count(item) for item in data)
            if isinstance(data, dict):
                count = 0
                if device_name in data:
                    count += len(data[device_name])
                for value in data.values():
                    count += recursive_count(value)
                return count
            return 0

        return recursive_count(self._boardfarm_config.env_config)

    def _replace(
        self,
        data: list[Any] | dict[Any, Any] | str,
        val_from: Any,  # noqa: ANN401
        val_to: Any,  # noqa: ANN401
    ) -> list[Any] | dict[Any, Any] | str:
        """Recursively replaces all instances of `val_from` with `val_to` in `data`.

        :param data: The input data structure (either a list or a dictionary).
        :type data: Union[List[Any], dict[Any, Any]]
        :param val_from: The value to be replaced.
        :type val_from: Any
        :param val_to: The value to replace `val_from` with.
        :type val_to: Any
        :return: `data` with all occurrences of `val_from` replaced by `val_to`
        :rtype: Union[List[Any], dict[Any, Any]]
        """
        if isinstance(data, list):
            return [self._replace(x, val_from, val_to) for x in data]
        if isinstance(data, dict):
            return {k: self._replace(v, val_from, val_to) for k, v in data.items()}
        return val_to if data == val_from else data

    def _generate_device_compose(self, device_name: str) -> dict[str, Any]:
        """Generate the compose json for the specified device.

        :param device_name: The name of the device for which yml has to be generated.
        :type device_name: str
        :return: The compose json for the specified device
        :rtype: dict[str, Any]
        """
        json_file_path = self._get_device_json_path(f"{device_name}")
        if not json_file_path.exists():
            return {}
        device_template = json.loads(json_file_path.read_text())
        requested_devices = self._get_requested_device_count(device_name.upper())
        device_compose: dict[str, Any] = {}
        for device_count in range(requested_devices):
            base_device = deepcopy(device_template)
            base_device = self._replace(
                base_device,
                device_name,
                f"{device_name}{device_count + 1}",
            )
            # This is needed because the name in schema(ext_voip) differs from actual
            # device name (softphone)
            if device_name == "ext_voip":
                base_device["services"][  # type: ignore[call-overload, index]
                    device_name
                ] = self._replace(
                    base_device["services"][  # type: ignore[call-overload, index]
                        device_name  # type: ignore[call-overload, index]
                    ],
                    f"{device_name}{device_count + 1}",
                    f"softphone{device_count + 1}",
                )
            if isinstance(base_device, dict):
                base_device["services"][device_name]["ports"] = self._update_ports(
                    base_device["services"][device_name]["ports"],
                    device_count,
                )
                base_device["services"][f"{device_name}{device_count + 1}"] = (
                    base_device["services"].pop(device_name)
                )
                device_compose = jsonmerge.merge(device_compose, base_device)
        return device_compose

    def _generate_base_compose(self) -> dict[str, Any]:
        """Load the base compose from a pre-defined template.

        :return: The base compose
        :rtype: dict[str, Any]
        """
        return json.loads(self._get_device_json_path().read_text())

    def _generate_orchestrator_compose(
        self,
        device_list: list[str],
    ) -> dict[str, Any]:
        """Generate the compose yml for orchestrator device.

        :param device_list: a list of devices the orchestrator depends on
        :type device_list: list[str]
        :return: the loaded compose yml for orchestrator device
        :rtype: dict[str, Any]
        """
        orchestrator_compose = json.loads(
            self._get_device_json_path("orchestrator").read_text(),
        )
        # We do not want the orchestrator depending on itself
        device_list.remove("orchestrator")
        orchestrator_compose["services"]["orchestrator"]["depends_on"] = sorted(
            device_list,
        )
        return orchestrator_compose

    def _merge_dicts(self, *dicts: dict[str, Any]) -> dict[str, Any]:
        merged_dict: dict[str, Any] = {}
        for dictionary in dicts:
            merged_dict = jsonmerge.merge(
                merged_dict,
                dictionary,
                {"recursiveMergeStrategy": "merge"},
            )
        return merged_dict

    def _get_devices(self, env_config: dict[str, Any]) -> None:
        """Recursively search for the names of the devices in the environment.

        .. hint:: The device names are identified from the json keys

        :param env_config: Boardfarm environment config
        :type env_config: dict[str, Any]
        """
        for config_key, config_value in env_config.items():
            if (
                isinstance(config_value, dict)
                and "device_type" not in config_value
                and config_key != "BOARD"
            ):
                self._get_devices(config_value)
            if isinstance(config_value, list) and config_key not in (
                "BOARD",
                "device_options",
            ):
                self._devices_list.append(config_key.lower())
            if isinstance(config_value, list) and config_key == "device_options":
                self._get_devices(next((item for item in config_value), {}))
            if config_key == "BOARD" and isinstance(config_value, list):
                self._get_devices(next((item for item in config_value), {}))

    def generate_docker_compose(self) -> dict[str, Any]:
        """Generate the docker-compose yml to be used as payload for docker factory.

        :return: The docker compose payload for docker factory
        :rtype: dict[str, Any]
        """
        base_compose = self._generate_base_compose()
        for device in sorted(self._devices_list):
            base_compose = self._merge_dicts(
                base_compose,
                self._generate_device_compose(device),
            )
        return jsonmerge.merge(
            base_compose,
            self._generate_orchestrator_compose(list(base_compose["services"].keys())),
        )
