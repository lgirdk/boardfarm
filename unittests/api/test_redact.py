"""Redaction of credentials in diagnostics output."""

from __future__ import annotations

import pytest

from boardfarm3.api.redact import REDACTED, is_secret_key, redact


def test_redacts_secret_looking_keys() -> None:
    out = redact({"username": "admin", "password": "hunter2", "authToken": "abc"})
    assert out["username"] == "admin"
    assert out["password"] == REDACTED
    assert out["authToken"] == REDACTED


def test_redacts_recursively_through_lists_and_dicts() -> None:
    out = redact({"devices": [{"name": "wan", "ssh_key": "PRIVATE"}]})
    assert out["devices"][0]["name"] == "wan"
    assert out["devices"][0]["ssh_key"] == REDACTED


def test_does_not_mutate_the_input() -> None:
    original = {"password": "hunter2"}
    redact(original)
    assert original["password"] == "hunter2"  # noqa: S105


def test_leaves_non_mapping_values_alone() -> None:
    assert redact("plain") == "plain"
    assert redact(42) == 42
    assert redact(None) is None


def test_credential_keys_are_redacted() -> None:
    value = {
        "ldap_credentials": "user;pw",
        "loc_res_credentials": "user;pw",
        "loc_res_url": "http://locker:8000",
    }
    assert redact(value) == {
        "ldap_credentials": REDACTED,
        "loc_res_credentials": REDACTED,
        "loc_res_url": "http://locker:8000",
    }


@pytest.mark.parametrize(
    ("name", "secret"),
    [
        ("ldap_credentials", True),
        ("PASSWORD", True),
        ("api_token", True),
        ("loc_res_url", False),
        ("board_name", False),
    ],
)
def test_is_secret_key_matches_the_redaction_rule(name: str, secret: bool) -> None:
    assert is_secret_key(name) is secret


@pytest.mark.parametrize("name", ["UIM_PWD", "ldap_pwd"])
def test_pwd_names_are_secret(name: str) -> None:
    assert is_secret_key(name) is True


def test_redacts_a_pwd_value() -> None:
    out = redact({"uim_pwd": "hunter2", "uim_user": "admin"})
    assert out == {"uim_pwd": REDACTED, "uim_user": "admin"}
