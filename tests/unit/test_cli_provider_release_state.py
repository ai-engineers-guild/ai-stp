"""Durable anti-rollback evidence cannot be lowered or supplied by a caller."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.commands import select
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import provider_releases
from ai_stp_cli.local.database import configured_path, open_registry

AT = "2026-08-08T10:00:00.000Z"
DIGEST_4 = "sha256:" + "4" * 64
DIGEST_6 = "sha256:" + "6" * 64
DIGEST_8 = "sha256:" + "8" * 64
PROVIDER = "claude-code"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def test_verified_history_advances_monotonically_and_repeats_idempotently(
    registry: sqlite3.Connection,
) -> None:
    assert provider_releases.minimum_sequence(registry, PROVIDER) == 0
    assert (
        provider_releases.record_verified(
            registry,
            provider_id=PROVIDER,
            sequence=4,
            artifact_digest=DIGEST_4,
            at=AT,
        )
        == 4
    )
    assert (
        provider_releases.record_verified(
            registry,
            provider_id=PROVIDER,
            sequence=8,
            artifact_digest=DIGEST_8,
            at=AT,
        )
        == 8
    )
    assert (
        provider_releases.record_verified(
            registry,
            provider_id=PROVIDER,
            sequence=8,
            artifact_digest=DIGEST_8,
            at=AT,
        )
        == 8
    )
    assert provider_releases.minimum_sequence(registry, PROVIDER) == 8


def test_lower_sequence_is_only_recovery_to_exact_prior_evidence(
    registry: sqlite3.Connection,
) -> None:
    for sequence, digest in ((4, DIGEST_4), (8, DIGEST_8)):
        provider_releases.record_verified(
            registry,
            provider_id=PROVIDER,
            sequence=sequence,
            artifact_digest=digest,
            at=AT,
        )

    assert (
        provider_releases.record_verified(
            registry,
            provider_id=PROVIDER,
            sequence=4,
            artifact_digest=DIGEST_4,
            at=AT,
        )
        == 8
    )
    with pytest.raises(CliFailure) as raised:
        provider_releases.record_verified(
            registry,
            provider_id=PROVIDER,
            sequence=6,
            artifact_digest=DIGEST_6,
            at=AT,
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert provider_releases.minimum_sequence(registry, PROVIDER) == 8
    assert not provider_releases.was_verified(
        registry,
        provider_id=PROVIDER,
        sequence=6,
        artifact_digest=DIGEST_6,
    )


def test_one_sequence_cannot_be_rebound_to_other_bytes(
    registry: sqlite3.Connection,
) -> None:
    provider_releases.record_verified(
        registry,
        provider_id=PROVIDER,
        sequence=8,
        artifact_digest=DIGEST_8,
        at=AT,
    )

    with pytest.raises(CliFailure) as raised:
        provider_releases.record_verified(
            registry,
            provider_id=PROVIDER,
            sequence=8,
            artifact_digest=DIGEST_6,
            at=AT,
        )

    assert raised.value.code == "AI_STP_CONFLICT"
    rows = registry.execute(
        "SELECT artifact_digest FROM verified_provider_release WHERE provider_id = ?",
        (PROVIDER,),
    ).fetchall()
    assert [row["artifact_digest"] for row in rows] == [DIGEST_8]


def test_incomplete_evidence_is_never_recorded(registry: sqlite3.Connection) -> None:
    with pytest.raises(CliFailure) as raised:
        provider_releases.record_verified(
            registry,
            provider_id=PROVIDER,
            sequence=-1,
            artifact_digest="not-a-digest",
            at="",
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def _manifest(path: Path, *, sequence: int) -> None:
    path.write_text(
        json.dumps(
            {
                "provider_id": PROVIDER,
                "provider_version": "1.0.0",
                "protocol_version": 1,
                "repository": "github.com/NDDev-OpenNetwork/claude-setup-system",
                "commit": "a" * 40,
                "license": "MIT",
                "artifact_url": "https://example.test/releases/1.0.0/provider",
                "artifact_size": 100,
                "artifact_digest": "sha256:" + "b" * 64,
                "entry_point": "provider",
                "supported_os": ["linux"],
                "supported_arch": ["x86_64"],
                "sequence": sequence,
                "policy_id": "nddev/provider/1",
                "publisher": "NDDev-OpenNetwork",
                "signing_key": "not-pinned",
                "signature_subject": "ai-stp:provider-release-manifest:v1",
                "signature": "not-pinned-and-never-trusted",
            }
        ),
        encoding="utf-8",
    )


def test_trust_command_reads_the_durable_floor_instead_of_caller_input(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    provider_releases.record_verified(
        registry,
        provider_id=PROVIDER,
        sequence=8,
        artifact_digest=DIGEST_8,
        at=AT,
    )
    place = tmp_path / "release.json"
    _manifest(place, sequence=6)

    view = select.provider_trust({"manifest": str(place)}).payload

    assert view.known_sequence == 8
    assert "sequence_rollback" in {item.code for item in view.refusals}


def test_trust_read_does_not_create_a_registry(tmp_path: Path) -> None:
    registry = configured_path()
    assert not registry.exists()
    place = tmp_path / "release.json"
    _manifest(place, sequence=6)

    view = select.provider_trust({"manifest": str(place)}).payload

    assert view.known_sequence == 0
    assert not registry.exists()


def test_trust_read_observes_zero_without_migrating_a_legacy_registry(tmp_path: Path) -> None:
    registry = configured_path()
    registry.parent.mkdir(mode=0o700, parents=True)
    with closing(sqlite3.connect(registry)) as connection:
        connection.execute("PRAGMA user_version=5")
    registry.chmod(0o600)
    place = tmp_path / "release.json"
    _manifest(place, sequence=6)

    view = select.provider_trust({"manifest": str(place)}).payload

    assert view.known_sequence == 0
    with closing(sqlite3.connect(registry)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE name = 'provider_release_floor'"
            ).fetchone()
            is None
        )
