"""Redaction of credential-bearing values in diagnostics output."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***"

# Matched against dict *keys* only, so a value that merely contains the word
# "key" is preserved.
_SECRET_KEY = re.compile(r"pass|passwd|password|secret|token|key|auth", re.IGNORECASE)


def redact(value: Any) -> Any:  # noqa: ANN401
    """Return a copy of *value* with credential-bearing values replaced.

    Recurses through dicts and lists. Only dict keys are inspected; scalars
    are returned unchanged. The input is never mutated.

    :param value: arbitrary JSON-compatible structure
    :type value: Any
    :return: redacted copy
    :rtype: Any
    """
    if isinstance(value, dict):
        return {
            key: REDACTED if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
