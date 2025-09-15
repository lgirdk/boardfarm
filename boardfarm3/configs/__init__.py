"""Boardfarm configs package."""

import json
from pathlib import Path

LOGGING_CONFIG = json.loads(
    (Path(__file__).parent / "logging.json").read_text(encoding="utf-8"),
)

GENERIC_DEVICE_MIBS_PATH = str((Path(__file__).parent / "mibs").resolve())

KIA_DHCP_IPV4_CONFIG_TEMPLATE = json.loads(
    (Path(__file__).parent / "kea_eth_provisioner4.conf").read_text(
        encoding="utf-8",
    ),
)
KIA_DHCP_IPV6_CONFIG_TEMPLATE = json.loads(
    (Path(__file__).parent / "kea_eth_provisioner6.conf").read_text(
        encoding="utf-8",
    ),
)
