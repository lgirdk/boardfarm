"""The stable id that marks which control plane owns a container."""

from __future__ import annotations

import os
import re
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

CONTROL_ID_ENV = "BOARDFARM_CONTROL_ID"
_VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def resolve_control_id(store_root: Path) -> str:
    """Return this control plane's id: env, else saved, else generated and saved.

    Never derived from the hostname: a re-created control container gets a new
    hostname and would orphan every agent it launched.

    :param store_root: the control store directory
    :type store_root: Path
    :return: the id stamped on every container as ``boardfarm.control_id``
    :rtype: str
    :raises ValueError: when ``BOARDFARM_CONTROL_ID`` is not a valid id
    """
    explicit = os.environ.get(CONTROL_ID_ENV, "").strip()
    if explicit:
        if not _VALID.match(explicit):
            msg = f"{CONTROL_ID_ENV} must match {_VALID.pattern}, got {explicit!r}"
            raise ValueError(msg)
        return explicit
    path = store_root / "control_id"
    try:
        saved = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        saved = ""
    if saved:
        return saved
    generated = f"c-{secrets.token_hex(4)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{generated}\n", encoding="utf-8")
    return generated
