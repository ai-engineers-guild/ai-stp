"""`harness status`: six answers, and why two sources are read to give them.

The interesting case is `lost`. A status built from the journal alone would
call an empty prefix a success, which is not hypothetical — a provider once
unpacked into a sandbox's own tmpfs, verified it where every check was true,
and reported `verified` for files that died with the namespace. The provider
was truthful; the prefix was empty. Reading the disk beside the journal is the
only thing that separates those.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.commands import harness
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation
from ai_stp_cli.local.database import configured_path, open_registry

AT = "2026-08-27T10:00:00.000Z"
SOON = "2026-08-27T11:00:00.000Z"
DIGEST = "sha256:" + "c" * 64
ENTRY = "bin/opencode"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _record(
    connection: sqlite3.Connection,
    prefix: Path,
    *,
    action: str,
    key: str,
    settle: str = "verified",
    version: str = "1.18.23",
    entry_point: str = ENTRY,
) -> installation.Plan:
    """Drive one program operation through the journal to a chosen outcome."""
    plan = installation.propose(
        connection,
        action=action,
        author="agent",
        target_id=str(prefix),
        expected_target_digest=DIGEST,
        provider_version="0.0.6",
        effects=("expose opencode",),
        recovery_action="remove",
        idempotency_key=key,
        at=AT,
        expires_at=SOON,
    )
    if settle == "planned":
        return plan
    installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=AT)
    installation.begin(connection, plan.operation_id, observed_target_digest=DIGEST, at=AT)
    installation.applied(connection, plan.operation_id, at=AT)
    if settle == "partial":
        installation.verify(connection, plan.operation_id, postconditions_met=False, at=AT)
        return plan
    installation.verify(connection, plan.operation_id, postconditions_met=True, at=AT)
    installation.record_program(
        connection, plan.operation_id, version=version, entry_point=entry_point
    )
    return plan


def _expose(prefix: Path, entry_point: str = ENTRY) -> Path:
    place = prefix / entry_point
    place.parent.mkdir(parents=True, exist_ok=True)
    place.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return place


def _status(prefix: Path) -> object:
    return harness.status({"harness": "opencode", "prefix": str(prefix)}).payload


def test_a_prefix_this_installation_never_touched_is_never_installed(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    del registry
    report = _status(tmp_path / "prefix")
    assert report.state == "never_installed"  # type: ignore[attr-defined]
    assert report.version == ""  # type: ignore[attr-defined]
    assert report.executable == ""  # type: ignore[attr-defined]


def test_a_verified_install_whose_bytes_are_there_is_present(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    prefix = tmp_path / "prefix"
    _expose(prefix)
    _record(registry, prefix, action="software_install", key="one")

    report = _status(prefix)
    assert report.state == "present"  # type: ignore[attr-defined]
    assert report.version == "1.18.23"  # type: ignore[attr-defined]
    assert report.entry_point == ENTRY  # type: ignore[attr-defined]
    assert report.executable == str(prefix / ENTRY)  # type: ignore[attr-defined]
    assert report.stopped == []  # type: ignore[attr-defined]


def test_a_verified_install_with_nothing_on_disk_is_lost(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """The journal says success and the prefix is empty. Nothing else reports this."""
    prefix = tmp_path / "prefix"
    _record(registry, prefix, action="software_install", key="one")

    report = _status(prefix)
    assert report.state == "lost"  # type: ignore[attr-defined]
    # The recorded facts survive: the operation really did happen, and an agent
    # recovering from this needs to know which one and what it claimed.
    assert report.version == "1.18.23"  # type: ignore[attr-defined]
    assert report.operation_id  # type: ignore[attr-defined]
    assert report.executable == ""  # type: ignore[attr-defined]
    assert "prefix" in report.reason  # type: ignore[attr-defined]


def test_a_verified_removal_leaves_removed_not_never_installed(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """An absence that reads as "never happened" invites a retry that cannot help."""
    prefix = tmp_path / "prefix"
    _record(registry, prefix, action="software_install", key="one")
    _record(registry, prefix, action="software_remove", key="two", entry_point=ENTRY)

    report = _status(prefix)
    assert report.state == "removed"  # type: ignore[attr-defined]


def test_a_sibling_copy_this_installation_did_not_write_is_foreign(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """The provider removes only what it installed; an unowned copy survives."""
    del registry
    prefix = tmp_path / "prefix"
    _expose(prefix)

    report = _status(prefix)
    assert report.state == "foreign"  # type: ignore[attr-defined]


def test_an_unsettled_operation_outranks_every_other_answer(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """It asks for an action rather than a reading, and usually explains the rest."""
    prefix = tmp_path / "prefix"
    _expose(prefix)
    _record(registry, prefix, action="software_install", key="one")
    _record(registry, prefix, action="software_update", key="two", settle="planned")

    report = _status(prefix)
    assert report.state == "interrupted"  # type: ignore[attr-defined]
    assert [item.operation for item in report.stopped] == ["software_update"]  # type: ignore[attr-defined]


def test_a_prefix_belonging_to_another_program_is_not_reported_here(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """One prefix, one answer. A neighbouring prefix is a different question."""
    mine = tmp_path / "mine"
    theirs = tmp_path / "theirs"
    _expose(mine)
    _record(registry, mine, action="software_install", key="one")

    report = _status(theirs)
    assert report.state == "never_installed"  # type: ignore[attr-defined]


def test_a_relative_prefix_is_refused_rather_than_resolved(tmp_path: Path) -> None:
    """The provider resolves it against nothing, so neither does this."""
    del tmp_path
    with pytest.raises(CliFailure) as raised:
        harness.status({"harness": "opencode", "prefix": "relative/prefix"})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_the_harness_is_required(tmp_path: Path) -> None:
    with pytest.raises(CliFailure) as raised:
        harness.status({"prefix": str(tmp_path)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_status_never_runs_the_program_it_reports(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `read` command does not execute a foreign binary to learn its version.

    The same reason `doctor` only checks that `gh` is present. Pinned because
    the version is the field most likely to tempt somebody into asking the
    program directly.
    """
    prefix = tmp_path / "prefix"
    _expose(prefix)
    _record(registry, prefix, action="software_install", key="one")

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("harness status must not spawn a process")

    monkeypatch.setattr("subprocess.run", refuse)
    monkeypatch.setattr("subprocess.Popen", refuse)

    report = _status(prefix)
    assert report.version == "1.18.23"  # type: ignore[attr-defined]
