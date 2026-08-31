"""`provider check` reads. It does not run what it is asking about, and it writes nothing.

Two defects, both of which a reader can state in one sentence each.

It ran the candidate. `_check_one` called `attested_bind.inspect_provider`, which
calls `provider-info` directly — no trust established first, no isolation
boundary, under the invoking user. A configured path can name any file on the
machine and a discovered one may have been replaced since it was installed, so a
command declared `read` was the cheapest way to get an arbitrary executable
started.

It wrote. `open_registry(create=True)` builds the database and its parent, moves
it to WAL, runs migrations and sets permissions; the handler then remembered an
observation and committed. A diagnostic answered its own question by writing,
and could not run at all against a read-only data directory.

The sentinel test below is the falsification: point the configuration at a
program that leaves a file behind when it starts, run the default command, and
require that the file does not exist.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from ai_stp_cli.commands import provider as provider_commands
from ai_stp_cli.local import provider_installations as installations

pytestmark = pytest.mark.cli


def _sentinel_executable(tmp_path: Path, sentinel: Path) -> Path:
    """A provider that proves it ran by writing a file, and answers nothing useful."""
    script = tmp_path / ("sentinel.cmd" if sys.platform == "win32" else "sentinel")
    if sys.platform == "win32":
        script.write_text(f"@echo off\r\necho ran > {sentinel}\r\n", encoding="utf-8")
    else:
        script.write_text(f'#!/bin/sh\ntouch "{sentinel}"\nprintf "{{}}"\n', encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A data directory of our own, so the test measures this command's writes."""
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    (home / "config").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    return home / "data"


def _configure(harness: str, executable: Path) -> None:
    """Point the configuration at one provider, the way a user would."""
    from ai_stp_cli.config import config_path

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Two levels in the file, three in the dotted key: the schema is closed and
    # declares `provider.paths.<harness>` as one field name (`#452`).
    path.write_text(f"provider:\n  paths.{harness}: {executable}\n", encoding="utf-8")


def test_a_configured_executable_is_not_started(
    tmp_path: Path, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The falsification: if it spawns, the sentinel exists."""
    sentinel = tmp_path / "it-ran"
    script = _sentinel_executable(tmp_path, sentinel)
    _configure("codex", script)

    answer = provider_commands.check({"harness": ["codex"], "offline": True})

    assert not sentinel.exists(), "provider check started an executable it only had to read"
    [outcome] = answer.payload.installations
    assert outcome.status == "unmanaged"
    assert outcome.provider_version == ""


def test_a_fresh_check_creates_nothing(isolated: Path) -> None:
    """A registry that does not exist is a history with nothing in it."""
    before = sorted(item.name for item in isolated.iterdir())

    provider_commands.check({"offline": True})

    assert sorted(item.name for item in isolated.iterdir()) == before


def test_a_read_only_data_directory_still_answers(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diagnostic that needs write permission is not a diagnostic."""
    if os.name == "nt":  # pragma: no cover - POSIX mode bits do not apply
        pytest.skip("directory mode is not the access control on Windows")
    isolated.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        answer = provider_commands.check({"offline": True})
    finally:
        isolated.chmod(stat.S_IRWXU)

    assert len(answer.payload.installations) == len(
        provider_commands._requested(None)  # pyright: ignore[reportPrivateUsage]
    )


def test_a_managed_provider_whose_bytes_changed_is_not_run(
    tmp_path: Path, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case that matters most: the manifest is real and the file is not its file."""
    sentinel = tmp_path / "it-ran"
    script = _sentinel_executable(tmp_path, sentinel)
    # A manifest naming a digest these bytes do not have. Whatever else is true,
    # this executable is not the one that was installed here.
    (script.parent / "release.json").write_text(
        '{"schema_version":1,"provider_id":"codex-setup-system",'
        '"provider_version":"0.0.48","protocol_version":3,'
        '"repository":"NDDev-OpenNetwork/codex-setup-system","commit":"' + "a" * 40 + '",'
        '"license":"Apache-2.0",'
        '"artifact_url":"https://github.com/NDDev-OpenNetwork/codex-setup-system/'
        'releases/download/0.0.48/codex-setup-system-linux-x86_64",'
        '"artifact_size":1024,"artifact_digest":"sha256:' + "b" * 64 + '",'
        '"entry_point":"codex-setup-system","supported_os":["linux"],'
        '"supported_arch":["x86_64"],"sequence":48,"policy_id":"opennetwork-1",'
        '"publisher":"NDDev-OpenNetwork","signing_key":"k","signature_subject":"s",'
        '"signature":"x"}',
        encoding="utf-8",
    )
    _configure("codex", script)

    answer = provider_commands.check({"harness": ["codex"], "offline": True})

    assert not sentinel.exists()
    [outcome] = answer.payload.installations
    assert outcome.status == "unmanaged"


def test_an_observation_does_not_become_a_remembered_choice(
    tmp_path: Path, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovery is not a decision. `#452` requires the choice to be explicit."""
    from ai_stp_cli.local.database import configured_path, open_registry

    registry = configured_path()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with open_registry(registry, create=True) as connection:
        connection.commit()

    script = _sentinel_executable(tmp_path, tmp_path / "unused")
    _configure("codex", script)
    provider_commands.check({"harness": ["codex"], "offline": True})

    with open_registry(registry) as connection:
        assert installations.remembered(connection, "codex") is None
