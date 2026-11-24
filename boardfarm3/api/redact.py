"""Redaction of credential-bearing values in diagnostics output."""

from __future__ import annotations

import re
from typing import Any

from boardfarm3.api.errors import scrub

REDACTED = "***"

# Matched against dict *keys* only, so a value that merely contains the word
# "key" is preserved. "cred" catches ldap_credentials and loc_res_credentials;
# "pwd" catches UIM_PWD and ldap_pwd. "passed" is not a secret: it is the
# pass count of a test run, a field name the run summary is fixed to.
_SECRET_KEY = re.compile(
    r"pass(?!ed)|passwd|password|secret|token|key|auth|cred|pwd", re.IGNORECASE
)


def is_secret_key(name: str) -> bool:
    """Return whether *name* names a credential-bearing value.

    :param name: a dict key or an option name
    :type name: str
    :return: True when redaction hides the value stored under *name*
    :rtype: bool
    """
    return _SECRET_KEY.search(name) is not None


def redact(value: Any) -> Any:  # noqa: ANN401
    """Return a copy of *value* with credential-bearing values replaced.

    Recurses through dicts and lists. A value under a secret-looking key is
    replaced whole; any other string is scrubbed of the credentials it embeds
    (``sshpass -p ...``, ``user:pw@`` URLs, ``password=...``). The input is
    never mutated.

    :param value: arbitrary JSON-compatible structure
    :type value: Any
    :return: redacted copy
    :rtype: Any
    """
    if isinstance(value, dict):
        return {
            key: REDACTED if is_secret_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return scrub(value) if isinstance(value, str) else value
