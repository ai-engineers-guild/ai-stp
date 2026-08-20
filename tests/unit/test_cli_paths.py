# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportPrivateImportUsage=false
"""Private files: created owner-only, replaced atomically, refused when widened."""

import os
import stat
from pathlib import Path

import pytest

from ai_stp_cli import paths
from ai_stp_cli.errors import CliFailure

# POSIX st_mode bits are not meaningful access control on Windows (ACLs govern).
# Production already skips mode enforcement when os.name == "nt"; tests must match.
_POSIX = os.name != "nt"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_a_new_private_file_is_owner_only(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "secret.txt"
    paths.write_private(target, "value")
    assert target.read_text(encoding="utf-8") == "value"
    if _POSIX:
        # POSIX-only: Windows reports a default mode (e.g. 0o666) even when protected.
        assert _mode(target) == paths.FILE_MODE
        assert _mode(target.parent) == paths.DIRECTORY_MODE


def test_private_binary_bytes_are_atomic_and_owner_only(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "artifact.bin"
    payload = bytes(range(256))
    paths.write_private_bytes(target, payload)
    assert target.read_bytes() == payload
    if _POSIX:
        assert _mode(target) == paths.FILE_MODE
        assert _mode(target.parent) == paths.DIRECTORY_MODE


def test_a_permissive_umask_does_not_widen_what_is_written(tmp_path: Path) -> None:
    # `mkdir` subtracts the umask, so a directory created under `0000` keeps
    # group and world bits unless the mode is applied again afterwards.
    previous = os.umask(0o000)
    try:
        target = tmp_path / "loose" / "secret.txt"
        paths.write_private(target, "value")
    finally:
        os.umask(previous)
    assert target.read_text(encoding="utf-8") == "value"
    if _POSIX:
        # POSIX-only: umask and st_mode owner bits are not the Windows ACL model.
        assert _mode(target) == paths.FILE_MODE
        assert _mode(target.parent) == paths.DIRECTORY_MODE


def test_rewriting_a_widened_file_does_not_write_through_its_mode(tmp_path: Path) -> None:
    # The defect this primitive exists for: applying `0600` only at creation
    # means a rewrite of a `chmod 644` file puts the new secret into a
    # world-readable file (`openai/codex#14704`).
    target = tmp_path / "secret.txt"
    paths.write_private(target, "first")
    target.chmod(0o644)
    paths.write_private(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    if _POSIX:
        # POSIX-only: rewrite must land under FILE_MODE, not the prior 0o644.
        assert _mode(target) == paths.FILE_MODE


@pytest.mark.skipif(
    not _POSIX,
    reason="POSIX mode widening is not enforced on Windows (paths.POSIX is false)",
)
def test_reading_a_widened_file_is_refused_rather_than_silently_accepted(tmp_path: Path) -> None:
    target = tmp_path / "secret.txt"
    paths.write_private(target, "value")
    target.chmod(0o604)
    with pytest.raises(CliFailure, match="readable by more than its owner") as raised:
        paths.read_private(target)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    # The message names the path with the home directory folded away.
    assert "mode" in raised.value.details


def test_bootstrap_lock_posix_path_with_mocked_fcntl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover the Unix flock branch even on Windows hosts (fcntl is mocked)."""
    import types

    fake_fcntl = types.SimpleNamespace(
        LOCK_EX=2,
        LOCK_NB=4,
        LOCK_UN=8,
        flock=lambda *_a, **_k: None,
    )
    monkeypatch.setattr(paths, "POSIX", True)
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(__import__("sys").modules, "fcntl", fake_fcntl)
    # Re-entrant nested acquisition.
    with paths.bootstrap_lock(timeout=1.0), paths.bootstrap_lock(timeout=1.0):
        pass

    # timeout path when flock always fails
    def _busy(*_a, **_k):
        raise OSError("busy")

    fake_fcntl.flock = _busy  # type: ignore[method-assign]
    monkeypatch.setattr(paths.time, "monotonic", lambda: 0.0)
    # After deadline: first call 0, subsequent > timeout
    calls = {"n": 0}

    def _mono() -> float:
        calls["n"] += 1
        return 0.0 if calls["n"] < 3 else 10.0

    monkeypatch.setattr(paths.time, "monotonic", _mono)
    monkeypatch.setattr(paths.time, "sleep", lambda _s: None)
    with pytest.raises(CliFailure) as raised, paths.bootstrap_lock(timeout=1.0):
        pass
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_failed_write_leaves_no_temporary_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The failure is injected at the last step, after the temporary file holds
    # the content: that is the moment a leftover would carry real material.
    target = tmp_path / "secret.txt"

    def refuse(self: Path, other: object) -> None:
        raise OSError("cross-device link")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="cross-device link"):
        paths.write_private(target, "value")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_is_private_reports_the_three_states(tmp_path: Path) -> None:
    absent = tmp_path / "absent"
    assert not paths.is_private(absent)
    present = tmp_path / "present"
    paths.write_private(present, "value")
    assert paths.is_private(present)
    if _POSIX:
        # POSIX-only: on Windows is_private is existence-only (modes are not the ACL).
        present.chmod(0o640)
        assert not paths.is_private(present)


def test_home_is_folded_away_but_a_path_outside_it_is_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Redacting is not shortening: a path outside the home directory is shown as
    # written, because hiding it would remove information rather than an account
    # name. Paths are built with pathlib so separators match the host OS.
    home = tmp_path / "home" / "example"
    home.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    nested = home / ".config" / "ai-stp"
    # Redacted machine paths always use POSIX separators (stable across OSes).
    assert paths.redact_home(nested) == "~/.config/ai-stp"
    assert paths.redact_home(home) == "~"
    outside = tmp_path / "srv" / "shared" / "ai-stp"
    assert paths.redact_home(outside) == str(outside).replace("\\", "/")
    # A different account whose name merely starts the same is not the home.
    similar = tmp_path / "home" / "example2" / "thing"
    assert paths.redact_home(similar) == str(similar).replace("\\", "/")


def test_the_layout_is_one_directory_under_the_data_home() -> None:
    assert paths.secrets_dir().parent == paths.data_dir()
    assert paths.device_file().parent == paths.data_dir()
    assert paths.data_dir().name == paths.APPLICATION_DIRECTORY


def test_the_bootstrap_lock_excludes_another_holder_and_gives_up_in_bounded_time() -> None:
    """Exclusive against a different holder, and never waited on for ever.

    A different thread rather than the same one: the lock is re-entrant for its
    holder, so asking twice on this thread is legal and proves nothing.
    """
    import concurrent.futures
    import time

    def contend() -> float:
        started = time.monotonic()
        try:
            with paths.bootstrap_lock(timeout=0.1):
                return -1.0  # pragma: no cover - the lock is held below
        except CliFailure as refusal:
            assert refusal.retryable is True
            assert "still setting this installation up" in refusal.message
            return time.monotonic() - started

    with paths.bootstrap_lock(), concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        waited = pool.submit(contend).result(timeout=10)

    assert 0.0 <= waited < 5.0

    # Released on the way out, so the next caller is not blocked by a corpse.
    with paths.bootstrap_lock(timeout=0.1):
        pass


def test_the_bootstrap_lock_can_be_re_entered_by_its_holder() -> None:
    """The bootstrap paths nest, and `flock` does not forgive that by itself.

    Creating the device passport takes the lock and then mints the owner, which
    takes it again. A second `open` is a different holder as far as the kernel
    is concerned, so without re-entry the process waits for itself until the
    timeout — which is exactly how six concurrent first runs failed before this
    was tracked. The short timeouts below are the assertion: they would expire.
    """
    with (
        paths.bootstrap_lock(),
        paths.bootstrap_lock(timeout=0.1),
        paths.bootstrap_lock(timeout=0.1),
    ):
        pass

    # Fully released once the outermost holder leaves, not left pinned by the
    # nesting counter.
    with paths.bootstrap_lock(timeout=0.1):
        pass
