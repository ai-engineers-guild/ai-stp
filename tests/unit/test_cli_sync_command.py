"""`sync preview` reaches the merge core and never changes local state."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.commands import sync
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, revisions
from ai_stp_cli.local.database import open_registry
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id

DEVICE = "device_01KZAA000000000000000000A0"
OTHER_DEVICE = "device_01KZAA000000000000000000B0"


@pytest.fixture
def registry(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        yield connection
    finally:
        connection.close()


def _content(
    stable_id: str,
    owner_id: str,
    at: str,
    *,
    parents: list[str] | None = None,
    facts: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "kind": "developer",
        "stable_id": stable_id,
        "owner_id": owner_id,
        "created_at": at,
        "visibility": "private",
        "parent_revision_ids": cast(list[JsonValue], parents or []),
        "facts": facts or {},
    }


def _branches(
    connection: sqlite3.Connection,
    *,
    left_facts: dict[str, JsonValue],
    right_facts: dict[str, JsonValue],
) -> tuple[revisions.StoredRevision, revisions.StoredRevision, revisions.StoredRevision]:
    stable_id, owner_id, at = new_id("developer"), new_id("account"), passports.moment()
    root = revisions.commit(connection, _content(stable_id, owner_id, at), device_id=DEVICE)
    left = revisions.commit(
        connection,
        _content(
            stable_id,
            owner_id,
            at,
            parents=[root.revision_id],
            facts=left_facts,
        ),
        device_id=DEVICE,
    )
    right = revisions.commit(
        connection,
        _content(
            stable_id,
            owner_id,
            at,
            parents=[root.revision_id],
            facts=right_facts,
        ),
        device_id=OTHER_DEVICE,
    )
    return root, left, right


def _fact(value: JsonValue) -> dict[str, JsonValue]:
    return {"value": value, "origin": "declared", "confirmation": "none"}


def test_independent_heads_produce_a_deterministic_merge_candidate(
    registry: sqlite3.Connection,
) -> None:
    root, left, right = _branches(
        registry,
        left_facts={"role": _fact("backend")},
        right_facts={"autonomy": _fact("full-auto")},
    )
    before = registry.serialize()

    report = sync._report(registry, root.stable_id)  # pyright: ignore[reportPrivateUsage]

    assert report.state == "merge_ready"
    assert report.common_ancestor_revision_id == root.revision_id
    assert report.head_revision_ids == sorted([left.revision_id, right.revision_id])
    assert report.candidate_revision_id is not None
    assert report.candidate_revision_id not in report.head_revision_ids
    assert report.affected_fields == []
    assert registry.serialize() == before


def test_same_field_divergence_names_only_the_conflicting_pointer(
    registry: sqlite3.Connection,
) -> None:
    root, _left, _right = _branches(
        registry,
        left_facts={"role": _fact("backend")},
        right_facts={"role": _fact("frontend")},
    )

    report = sync._report(registry, root.stable_id)  # pyright: ignore[reportPrivateUsage]

    assert report.state == "conflict"
    assert report.candidate_revision_id is None
    assert report.affected_fields == ["/facts/role/value"]

    before = registry.serialize()
    with pytest.raises(CliFailure) as conflict:
        sync.commit_merge(registry, stable_id=root.stable_id, device_id=DEVICE)
    assert conflict.value.code == "AI_STP_CONFLICT"
    assert registry.serialize() == before


def test_one_head_is_up_to_date_and_a_missing_entity_is_typed(
    registry: sqlite3.Connection,
) -> None:
    stable_id, owner_id, at = new_id("developer"), new_id("account"), passports.moment()
    stored = revisions.commit(registry, _content(stable_id, owner_id, at), device_id=DEVICE)

    report = sync._report(registry, stable_id)  # pyright: ignore[reportPrivateUsage]
    assert report.state == "up_to_date"
    assert report.candidate_revision_id == stored.revision_id

    with pytest.raises(CliFailure) as raised:
        sync._report(registry, new_id("developer"))  # pyright: ignore[reportPrivateUsage]
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_an_ancestor_head_is_classified_as_fast_forward(
    registry: sqlite3.Connection,
) -> None:
    stable_id, owner_id, at = new_id("developer"), new_id("account"), passports.moment()
    root = revisions.commit(registry, _content(stable_id, owner_id, at), device_id=DEVICE)
    child = revisions.commit(
        registry,
        _content(
            stable_id,
            owner_id,
            at,
            parents=[root.revision_id],
            facts={"role": _fact("backend")},
        ),
        device_id=DEVICE,
    )
    registry.execute(
        "INSERT INTO head (stable_id, revision_id) VALUES (?, ?)",
        (stable_id, root.revision_id),
    )

    report = sync._report(registry, stable_id)  # pyright: ignore[reportPrivateUsage]

    assert report.state == "fast_forward"
    assert report.common_ancestor_revision_id == root.revision_id
    assert report.candidate_revision_id == child.revision_id
