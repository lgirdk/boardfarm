"""Type hints for jc parsed output."""

from __future__ import annotations

from typing import TypedDict


class ParsedPSOutput(TypedDict):
    """Typing for parsed output returned by jc for the ps command."""

    pid: int
    tty: str | None
    time: str
    cmd: str
