"""Native fault and cleanup helpers retain unrelated fixture resources."""

from __future__ import annotations

import logging
import stat
from pathlib import Path

import pytest
from tests.support.api_settings import close_api_log_files
from tests.support.native_credentials import lose_enrollment_key
from tests.support.native_files import file_protection

DEVICE = "device_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def test_file_key_loss_removes_only_the_owned_enrollment(tmp_path: Path) -> None:
    namespace = tmp_path / "ai-stp-v2-connections"
    namespace.mkdir()
    key = namespace / f"device-key.{DEVICE}"
    key.write_bytes(b"owned fixture key")
    other = namespace / "unrelated"
    other.write_bytes(b"retained")
    lose_enrollment_key(tmp_path, DEVICE, "file")
    assert not key.exists() and other.read_bytes() == b"retained"


def test_os_key_loss_refuses_before_native_access_on_a_developer_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(AssertionError, match="Native fixtures require hosted CI"):
        lose_enrollment_key(tmp_path, DEVICE, "os_keyring")


def test_api_log_cleanup_closes_only_files_inside_the_owned_directory(tmp_path: Path) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    own = logging.FileHandler(owned / "api.log")
    other = logging.FileHandler(tmp_path / "unrelated.log")
    root = logging.getLogger()
    root.addHandler(own)
    root.addHandler(other)
    try:
        close_api_log_files(owned)
        assert own.stream is None
        assert other.stream is not None and other in root.handlers
        (owned / "api.log").unlink()
    finally:
        root.removeHandler(own)
        root.removeHandler(other)
        own.close()
        other.close()


def test_file_protection_observes_a_native_read_only_change(tmp_path: Path) -> None:
    path = tmp_path / "unowned"
    path.write_bytes(b"preserved")
    before = file_protection(path)
    try:
        path.chmod(stat.S_IREAD)
        assert file_protection(path) != before
        assert path.read_bytes() == b"preserved"
    finally:
        path.chmod(before.mode)
    assert file_protection(path) == before
