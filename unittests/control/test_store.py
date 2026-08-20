"""On-disk diagnostics store."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from boardfarm3_control.store import DiagnosticsStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="store")
def store_fixture(tmp_path: Path) -> DiagnosticsStore:
    """Return a store rooted in a temporary directory.

    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    :return: store under test
    :rtype: DiagnosticsStore
    """
    return DiagnosticsStore(root=tmp_path)


def test_meta_round_trips(store: DiagnosticsStore) -> None:
    store.write_meta("s-1", {"board_name": "board", "ended_at": 1.0})
    assert store.read_meta("s-1") == {"board_name": "board", "ended_at": 1.0}


def test_read_meta_for_unknown_session_is_none(store: DiagnosticsStore) -> None:
    assert store.read_meta("nope") is None


def test_write_bundle_returns_byte_count(store: DiagnosticsStore) -> None:
    written = store.write_bundle("s-1", [b"abc", b"de"])
    assert written == 5
    assert store.has_bundle("s-1")
    assert store.bundle_path("s-1").read_bytes() == b"abcde"


def test_list_sessions_and_total_bytes(store: DiagnosticsStore) -> None:
    store.write_bundle("s-1", [b"a" * 10])
    store.write_bundle("s-2", [b"b" * 20])
    assert sorted(store.list_sessions()) == ["s-1", "s-2"]
    assert store.total_bytes() >= 30


def test_delete_removes_everything_for_a_session(store: DiagnosticsStore) -> None:
    store.write_meta("s-1", {"board_name": "board"})
    store.write_bundle("s-1", [b"abc"])
    store.delete("s-1")
    assert store.list_sessions() == []
    assert not store.session_dir("s-1").exists()


def test_root_defaults_to_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path / "custom"))
    assert (
        DiagnosticsStore().session_dir("s-1")
        == tmp_path / "custom" / "sessions" / "s-1"
    )
