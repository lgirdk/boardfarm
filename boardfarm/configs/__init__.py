"""Boardfarm configs package."""

import json
from pathlib import Path

LOGGING_CONFIG = json.loads(
    (Path(__file__).parent / "logging.json").read_text(encoding="utf-8")
)

GENERIC_DEVICE_MIBS_PATH = str(
    (Path(__file__).parent / ".." / ".." / "resources" / "mibs").resolve()
)
