"""An acquired version is not the user's own work (`#447`).

Everything in the local registry claimed `owned_or_pinned=True`, on the
reasoning that it was adopted or authored here. `registry acquire` materialises
a published setup and its exact graph into the same tables, so that reasoning
stopped being true the moment the command existed — and `lane_of` checks
ownership first, which put somebody else's object in the
`local_owner_or_pinned` lane and past the unverified-consent question, the
licence and the grant in one step.

An excess permission rather than a missing refusal, which is why the repair
records what the catalogue said instead of adding a check.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ai_stp_cli.local import acquired_trust, database, search


def _registry(tmp_path: Path) -> sqlite3.Connection:
    return database.open_registry(tmp_path / "registry.sqlite3", create=True)


def test_a_recorded_verdict_survives_a_round_trip(tmp_path: Path) -> None:
    connection = _registry(tmp_path)
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        ("component_01TESTACQUIRED0000000000", "2026-08-29T00:00:00.000Z"),
    )
    acquired_trust.record(
        connection,
        stable_id="component_01TESTACQUIRED0000000000",
        version="1.0",
        passport_digest="sha256:" + "a" * 64,
        verdict=acquired_trust.Verdict(
            trust_lane="experimental", author_verified=False, component_verified=True
        ),
        at="2026-08-29T00:00:00.000Z",
    )

    held = acquired_trust.verdicts(connection)
    assert held[("component_01TESTACQUIRED0000000000", "1.0")] == acquired_trust.Verdict(
        trust_lane="experimental", author_verified=False, component_verified=True
    )


def test_recording_the_same_exact_version_twice_is_a_replay(tmp_path: Path) -> None:
    """A published `X.Y` is immutable, so it cannot carry two verdicts."""
    connection = _registry(tmp_path)
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        ("component_01TESTACQUIRED0000000000", "2026-08-29T00:00:00.000Z"),
    )
    for lane in ("experimental", "authoritative"):
        acquired_trust.record(
            connection,
            stable_id="component_01TESTACQUIRED0000000000",
            version="1.0",
            passport_digest="sha256:" + "a" * 64,
            verdict=acquired_trust.Verdict(
                trust_lane=lane, author_verified=False, component_verified=False
            ),
            at="2026-08-29T00:00:00.000Z",
        )
    held = acquired_trust.verdicts(connection)
    assert len(held) == 1
    assert held[("component_01TESTACQUIRED0000000000", "1.0")].trust_lane == "experimental"


def test_an_unconfirmed_acquired_object_is_experimental_not_the_users_own() -> None:
    """The lane the excess permission was hiding.

    `lane_of` checks ownership first — deliberately, so nobody is asked to
    consent to their own work — which is exactly why claiming ownership for an
    acquired object skipped the question entirely.
    """
    acquired = search.Candidate(
        stable_id="component_01TESTACQUIRED0000000000",
        revision_id="revision_01TEST",
        fields={},
        owned_or_pinned=False,
        author_verified=False,
        component_verified=False,
    )
    lane, reason = search.lane_of(acquired)
    assert lane == search.LANE_EXPERIMENTAL
    assert "not confirmed" in reason

    authored = search.Candidate(
        stable_id="component_01TESTAUTHORED00000000",
        revision_id="revision_01TEST",
        fields={},
        owned_or_pinned=True,
    )
    assert search.lane_of(authored)[0] == search.LANE_LOCAL
