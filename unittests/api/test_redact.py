"""Redaction of credentials in diagnostics output."""

from __future__ import annotations

from boardfarm3.api.redact import REDACTED, redact


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
