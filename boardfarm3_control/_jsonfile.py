"""Small JSON files the control plane owns, written atomically."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def read_json(path: Path) -> Any:  # noqa: ANN401
    """Read a JSON document.

    :param path: file to read
    :type path: Path
    :return: the decoded document
    :rtype: Any
    """
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: Any) -> None:  # noqa: ANN401
    """Write *data* through a temporary file and a rename, so readers never see half a file.

    :param path: destination file
    :type path: Path
    :param data: JSON-serialisable document
    :type data: Any
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
