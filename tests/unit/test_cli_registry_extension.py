"""The registry extension: content store, drafts, overlays, consent and tombstones.

Mostly failure and concurrency, because those are what `#159` asks to be proved
and what a store gets wrong quietly rather than loudly.
"""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import consent, content, database, lifecycle, revisions
from ai_stp_cli.local.database import configured_path, open_registry

MOMENT = "2026-08-07T10:00:00.000Z"
LATER = "2026-08-07T11:00:00.000Z"
OWNER = "account_01J0000000000000000000000A"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _entity(connection: sqlite3.Connection, stable_id: str, kind: str = "component") -> str:
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?)",
        (stable_id, kind, MOMENT),
    )
    return stable_id


def _passport(
    stable_id: str, *, state: str | None = None, mark: str = "a", kind: str = "component"
) -> dict[str, object]:
    content_document: dict[str, object] = {
        "schema_version": 1,
        "kind": kind,
        "stable_id": stable_id,
        "owner_id": OWNER,
        "created_at": MOMENT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {
            "mark": {
                "value": mark,
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            }
        },
    }
    if state is not None:
        content_document["lifecycle_state"] = state
    return content_document


# --- content store --------------------------------------------------------


def test_bytes_are_addressed_by_their_own_digest(registry: sqlite3.Connection) -> None:
    stored = content.put(registry, b"the exact bytes", at=MOMENT)
    assert stored.digest == content.address_of(b"the exact bytes")
    assert stored.byte_length == len(b"the exact bytes")
    assert content.get(registry, stored.digest) == b"the exact bytes"


def test_storing_the_same_bytes_twice_stores_one_row(registry: sqlite3.Connection) -> None:
    first = content.put(registry, b"same", at=MOMENT)
    second = content.put(registry, b"same", at=LATER)

    assert first.digest == second.digest
    # The row that is already there is the row that would have been written, so
    # the second put keeps the first moment rather than rewriting it.
    assert second.stored_at == MOMENT
    held = registry.execute("SELECT COUNT(*) AS n FROM content").fetchone()
    assert held["n"] == 1


def test_different_bytes_never_share_an_address(registry: sqlite3.Connection) -> None:
    assert content.address_of(b"a") != content.address_of(b"b")
    # Including bytes that are not text at all: the column is a BLOB because a
    # component may be anything its author wrote.
    raw = bytes(range(256))
    stored = content.put(registry, raw, at=MOMENT)
    assert content.get(registry, stored.digest) == raw


def test_reading_an_object_that_changed_underneath_is_refused(
    registry: sqlite3.Connection,
) -> None:
    stored = content.put(registry, b"original", at=MOMENT)
    registry.execute("UPDATE content SET bytes = ? WHERE digest = ?", (b"swapped", stored.digest))

    # The address is the integrity proof, so an object that no longer hashes to
    # the address it is filed under is a conflict, not a successful read.
    with pytest.raises(CliFailure, match="no longer matches the address") as raised:
        content.get(registry, stored.digest)
    assert raised.value.code == "AI_STP_CONFLICT"


def test_an_absent_address_and_an_oversized_object_are_named_differently(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CliFailure, match="no object is stored") as missing:
        content.get(registry, content.address_of(b"never stored"))
    assert missing.value.code == "AI_STP_NOT_FOUND"

    monkeypatch.setattr(content, "MAX_CONTENT_BYTES", 4)
    with pytest.raises(CliFailure, match="larger than the local store accepts"):
        content.put(registry, b"far too many bytes", at=MOMENT)


def test_computing_an_address_stores_nothing(registry: sqlite3.Connection) -> None:
    # A plan has to name what it would write before writing it, and naming it
    # must not be the writing.
    content.address_of(b"planned")
    assert registry.execute("SELECT COUNT(*) AS n FROM content").fetchone()["n"] == 0


# --- drafts ---------------------------------------------------------------


def test_a_draft_is_excluded_from_registration_and_a_finished_one_is_not(
    registry: sqlite3.Connection,
) -> None:
    # `project` because it is a mutable kind: `component` and `setup` are
    # snapshots the envelope forbids from having parents, so a draft of one of
    # those is a separate snapshot rather than an earlier link in a chain.
    held = _entity(registry, "project_01J0000000000000000000000B", kind="project")
    drafted = revisions.commit(
        registry,
        _passport(held, state="draft", kind="project"),  # pyright: ignore[reportArgumentType]
        device_id="device_test",
    )
    assert lifecycle.registrable(registry, drafted) is False
    assert lifecycle.is_draft(drafted)

    # Finishing it is a content change and therefore a revision.
    finished = _passport(held, state="complete", kind="project")
    finished["parent_revision_ids"] = [drafted.revision_id]
    stored = revisions.commit(registry, finished, device_id="device_test")  # pyright: ignore[reportArgumentType]
    assert lifecycle.registrable(registry, stored) is True


def test_a_draft_snapshot_of_an_immutable_kind_needs_no_chain(
    registry: sqlite3.Connection,
) -> None:
    """`component` and `setup` are snapshots, so a draft is a separate one.

    The envelope refuses a parent on an immutable kind, which means finishing a
    draft component cannot be "the next revision of it". It is another snapshot,
    and only the finished one is registrable — exactly what `REQ-509` wants: an
    incomplete draft may sync privately and must not be registered or ranked.
    """
    held = _entity(registry, "component_01J0000000000000000000000B")
    drafted = revisions.commit(registry, _passport(held, state="draft"), device_id="device_test")  # pyright: ignore[reportArgumentType]
    finished = revisions.commit(registry, _passport(held, state="complete"), device_id="device_x")  # pyright: ignore[reportArgumentType]

    assert drafted.parents == ()
    assert lifecycle.registrable(registry, drafted) is False
    assert lifecycle.registrable(registry, finished) is True


def test_a_passport_that_declares_nothing_is_complete(registry: sqlite3.Connection) -> None:
    held = _entity(registry, "component_01J0000000000000000000000C")
    stored = revisions.commit(registry, _passport(held), device_id="device_test")  # pyright: ignore[reportArgumentType]

    # Every passport written before drafts existed is finished. Reading silence
    # as `draft` would retroactively hide all of them.
    assert lifecycle.declared_state(stored) == lifecycle.STATE_COMPLETE
    assert lifecycle.registrable(registry, stored) is True


def test_declaring_a_state_nobody_defined_is_refused(registry: sqlite3.Connection) -> None:
    held = _entity(registry, "component_01J0000000000000000000000D")
    stored = revisions.commit(registry, _passport(held, state="nearly-done"), device_id="device_x")  # pyright: ignore[reportArgumentType]

    with pytest.raises(CliFailure, match="unknown lifecycle state"):
        lifecycle.declared_state(stored)


def test_a_registrable_revision_of_a_deleted_entity_is_still_hidden(
    registry: sqlite3.Connection,
) -> None:
    held = _entity(registry, "component_01J0000000000000000000000E")
    stored = revisions.commit(registry, _passport(held), device_id="device_test")  # pyright: ignore[reportArgumentType]
    assert lifecycle.registrable(registry, stored) is True

    lifecycle.entomb(registry, held, reason="the user deleted it", at=MOMENT)
    # Deletion is a fact about the entity and outranks a finished revision.
    assert lifecycle.registrable(registry, stored) is False


def test_declaring_a_draft_state_changes_the_sealed_revision(
    registry: sqlite3.Connection,
) -> None:
    """The state is inside the hashed bytes, and that is the design.

    A published version's lifecycle deliberately stays *outside* them, because a
    published version is immutable. Completeness is the other case: finishing a
    draft is a change to the passport and must produce a revision saying so.
    """
    one = _entity(registry, "component_01J0000000000000000000000F")
    two = _entity(registry, "component_01J0000000000000000000000G")
    plain = revisions.commit(registry, _passport(one), device_id="device_test")  # pyright: ignore[reportArgumentType]
    drafted = revisions.commit(registry, _passport(two, state="draft"), device_id="device_test")  # pyright: ignore[reportArgumentType]
    assert plain.revision_id != drafted.revision_id


# --- overlay provenance ---------------------------------------------------


def test_an_overlay_records_where_it_came_from_and_what_it_was_applied_to(
    registry: sqlite3.Connection,
) -> None:
    held = _entity(registry, "component_01J0000000000000000000000H")
    stored = revisions.commit(registry, _passport(held), device_id="device_test")  # pyright: ignore[reportArgumentType]
    base = content.address_of(b"the base")

    recorded = lifecycle.record_overlay(
        registry,
        revision_id=stored.revision_id,
        source_kind="local_file",
        source_ref="overlays/team.md",
        base_digest=base,
        at=MOMENT,
    )
    assert recorded.base_digest == base
    assert lifecycle.overlay_of(registry, stored.revision_id) == recorded
    # A revision that was not produced by an overlay says so by absence.
    assert lifecycle.overlay_of(registry, "revision_" + "0" * 64) is None


def test_an_overlay_provenance_is_written_once_and_never_moved(
    registry: sqlite3.Connection,
) -> None:
    held = _entity(registry, "component_01J0000000000000000000000J")
    stored = revisions.commit(registry, _passport(held), device_id="device_test")  # pyright: ignore[reportArgumentType]
    first = lifecycle.record_overlay(
        registry,
        revision_id=stored.revision_id,
        source_kind="local_file",
        source_ref="first.md",
        base_digest=content.address_of(b"base"),
        at=MOMENT,
    )
    again = lifecycle.record_overlay(
        registry,
        revision_id=stored.revision_id,
        source_kind="generated",
        source_ref="second.md",
        base_digest=content.address_of(b"other"),
        at=LATER,
    )
    # The version this produced is immutable, so its provenance is too.
    assert again == first


@pytest.mark.parametrize(
    ("kind", "ref", "base", "expected"),
    [
        ("smuggled", "a", "b", "must be one of"),
        ("local_file", "", "b", "name both its source"),
        ("local_file", "a", "", "name both its source"),
    ],
)
def test_an_overlay_without_a_named_origin_is_refused(
    registry: sqlite3.Connection, kind: str, ref: str, base: str, expected: str
) -> None:
    with pytest.raises(CliFailure, match=expected):
        lifecycle.record_overlay(
            registry,
            revision_id="revision_" + "0" * 64,
            source_kind=kind,
            source_ref=ref,
            base_digest=base,
            at=MOMENT,
        )


# --- tombstones -----------------------------------------------------------


def test_a_tombstone_hides_an_entity_without_removing_its_revisions(
    registry: sqlite3.Connection,
) -> None:
    held = _entity(registry, "component_01J0000000000000000000000K")
    stored = revisions.commit(registry, _passport(held), device_id="device_test")  # pyright: ignore[reportArgumentType]
    assert lifecycle.registrable(registry, stored) is True

    lifecycle.entomb(registry, held, reason="the user deleted it", at=MOMENT)

    assert lifecycle.registrable(registry, stored) is False
    # The history survives: `SPEC-013` REQ-1308 asks for a mark before physical
    # purge, not for the purge itself.
    assert revisions.get(registry, stored.revision_id) is not None


def test_replaying_a_tombstone_is_safe_and_keeps_the_first_mark(
    registry: sqlite3.Connection,
) -> None:
    held = _entity(registry, "component_01J0000000000000000000000M")
    revisions.commit(registry, _passport(held), device_id="device_test")  # pyright: ignore[reportArgumentType]

    first = lifecycle.entomb(registry, held, reason="deleted by the user", at=MOMENT)
    replayed = lifecycle.entomb(registry, held, reason="replayed from sync", at=LATER)

    # The deletion happened once. A replayed event carrying a later moment must
    # not move the record, or every sync would rewrite when it happened.
    assert replayed == first
    assert registry.execute("SELECT COUNT(*) AS n FROM tombstone").fetchone()["n"] == 1


def test_entombing_something_that_was_never_registered_is_refused(
    registry: sqlite3.Connection,
) -> None:
    with pytest.raises(CliFailure, match="nothing is registered") as raised:
        lifecycle.entomb(registry, "component_01J000000000000000000000ZZ", reason="x", at=MOMENT)
    assert raised.value.code == "AI_STP_NOT_FOUND"


# --- consent --------------------------------------------------------------


def _capabilities(**named: list[str]) -> dict[str, object]:
    return {name: list(value) for name, value in named.items()}


def test_a_consent_records_the_shape_the_candidate_had(registry: sqlite3.Connection) -> None:
    record = consent.grant(
        registry,
        consent_id="request_01J0000000000000000000000N",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint=consent.fingerprint_of(_capabilities(network_permissions=["api.acme.test"])),  # pyright: ignore[reportArgumentType]
        decided_by=OWNER,
        origin="registry search",
        at=MOMENT,
    )
    assert record.active
    assert record.fingerprint["network_permissions"] == ["api.acme.test"]
    # Every declared field is present even when the candidate asked for none:
    # an absent field and an empty one must not compare differently later.
    assert set(record.fingerprint) == set(consent.FINGERPRINT_FIELDS)
    assert consent.active(registry) == (record,)


def test_a_fingerprint_carries_only_the_declared_fields(registry: sqlite3.Connection) -> None:
    reduced = consent.fingerprint_of(
        {
            "network_permissions": ["a.test"],
            "AWS_SECRET_ACCESS_KEY": "AKIAIOSFODNN7EXAMPLE",
            "shell_history": ["rm -rf /"],
        }
    )
    # Built by naming what goes in. A record is forbidden to hold secrets or
    # environment values, and a whitelist cannot carry what nobody listed.
    assert set(reduced) == set(consent.FINGERPRINT_FIELDS)
    assert "AKIAIOSFODNN7EXAMPLE" not in str(reduced)
    assert "shell_history" not in reduced


def test_a_candidate_asking_for_more_than_recorded_is_no_longer_covered() -> None:
    record = consent.Record(
        consent_id="request_01J0000000000000000000000P",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint=consent.fingerprint_of(_capabilities(network_permissions=["api.acme.test"])),  # pyright: ignore[reportArgumentType]
        decided_by=OWNER,
        origin="registry search",
        created_at=MOMENT,
        revoked_at=None,
    )

    same = consent.covers(record, _capabilities(network_permissions=["api.acme.test"]))  # pyright: ignore[reportArgumentType]
    assert same.covered

    grown = consent.covers(
        record,
        _capabilities(network_permissions=["api.acme.test", "collect.elsewhere.test"]),  # pyright: ignore[reportArgumentType]
    )
    assert not grown.covered
    # The contract requires the exact cause, not "something changed".
    assert grown.changed == ("network_permissions",)
    assert "more than when consent was given" in grown.reason


def test_a_candidate_asking_for_less_stays_covered() -> None:
    record = consent.Record(
        consent_id="request_01J0000000000000000000000Q",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint=consent.fingerprint_of(
            _capabilities(network_permissions=["a.test", "b.test"], process_permissions=["spawn"])  # pyright: ignore[reportArgumentType]
        ),
        decided_by=OWNER,
        origin="registry search",
        created_at=MOMENT,
        revoked_at=None,
    )
    # Consent was given to a shape, and a smaller shape is inside it. Treating a
    # removed permission as a reason to ask again would train users to say yes.
    assert consent.covers(record, _capabilities(network_permissions=["a.test"])).covered  # pyright: ignore[reportArgumentType]


def test_a_new_major_line_is_not_covered_by_the_previous_ones_consent() -> None:
    record = consent.Record(
        consent_id="request_01J0000000000000000000000R",
        scope=consent.SCOPE_OBJECT_MAJOR,
        target="component_01J0000000000000000000000S@2",
        fingerprint=consent.fingerprint_of({}),
        decided_by=OWNER,
        origin="registry show",
        created_at=MOMENT,
        revoked_at=None,
    )
    assert consent.covers(record, {}, major=2).covered
    third = consent.covers(record, {}, major=3)
    assert not third.covered
    assert "major line 2" in third.reason


def test_revoking_takes_effect_immediately_and_leaves_the_record(
    registry: sqlite3.Connection,
) -> None:
    record = consent.grant(
        registry,
        consent_id="request_01J0000000000000000000000T",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint=consent.fingerprint_of({}),
        decided_by=OWNER,
        origin="registry search",
        at=MOMENT,
    )
    assert consent.revoke(registry, scope=record.scope, target=record.target, at=LATER) is True

    withdrawn = consent.held(registry, scope=record.scope, target=record.target)
    assert withdrawn is not None and not withdrawn.active
    assert consent.covers(withdrawn, {}).reason == "the consent was withdrawn"
    assert consent.active(registry) == ()
    # Revoking twice is not an error and does not move the moment.
    assert consent.revoke(registry, scope=record.scope, target=record.target, at=MOMENT) is False


def test_re_granting_replaces_the_record_rather_than_adding_a_second(
    registry: sqlite3.Connection,
) -> None:
    for moment, hosts in ((MOMENT, ["a.test"]), (LATER, ["a.test", "b.test"])):
        consent.grant(
            registry,
            consent_id=f"request_01J000000000000000000000{moment[-3]}0",
            scope=consent.SCOPE_PUBLISHER,
            target="publisher/acme",
            fingerprint=consent.fingerprint_of(_capabilities(network_permissions=hosts)),  # pyright: ignore[reportArgumentType]
            decided_by=OWNER,
            origin="registry search",
            at=moment,
        )
    held = registry.execute("SELECT COUNT(*) AS n FROM consent").fetchone()
    # Two records for one target would make "which fingerprint applies" a
    # question with two answers.
    assert held["n"] == 1
    current = consent.held(registry, scope=consent.SCOPE_PUBLISHER, target="publisher/acme")
    assert current is not None and current.created_at == LATER


def test_re_granting_a_revoked_target_makes_it_active_again(
    registry: sqlite3.Connection,
) -> None:
    grant = {
        "scope": consent.SCOPE_PUBLISHER,
        "target": "publisher/acme",
        "fingerprint": consent.fingerprint_of({}),
        "decided_by": OWNER,
        "origin": "registry search",
    }
    consent.grant(registry, consent_id="request_01J0000000000000000000000V", at=MOMENT, **grant)  # pyright: ignore[reportArgumentType]
    consent.revoke(registry, scope=consent.SCOPE_PUBLISHER, target="publisher/acme", at=LATER)
    again = consent.grant(
        registry,
        consent_id="request_01J0000000000000000000000W",
        at=LATER,
        **grant,  # pyright: ignore[reportArgumentType]
    )
    assert again.active


@pytest.mark.parametrize(
    ("scope", "target", "expected"),
    [
        ("everything", "x", "must be one of"),
        # A wildcard target under a valid scope would restore the removed
        # `search.include_unverified` key under another name.
        (consent.SCOPE_PUBLISHER, "", "must name what it covers"),
    ],
)
def test_a_consent_that_covers_nothing_definite_is_refused(
    registry: sqlite3.Connection, scope: str, target: str, expected: str
) -> None:
    with pytest.raises(CliFailure, match=expected):
        consent.grant(
            registry,
            consent_id="request_01J0000000000000000000000X",
            scope=scope,
            target=target,
            fingerprint={},
            decided_by=OWNER,
            origin="registry search",
            at=MOMENT,
        )


def test_a_fingerprint_field_written_as_a_bare_value_still_compares(
    registry: sqlite3.Connection,
) -> None:
    # A record synced from another device may spell a single-valued field as a
    # scalar. Comparing it as a set is what keeps that from reading as "empty",
    # which would silently make everything look like an expansion.
    record = consent.Record(
        consent_id="request_01J0000000000000000000000Y",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint={"network_permissions": "a.test", "external_endpoints": None},
        decided_by=OWNER,
        origin="sync",
        created_at=MOMENT,
        revoked_at=None,
    )
    assert consent.covers(record, _capabilities(network_permissions=["a.test"])).covered  # pyright: ignore[reportArgumentType]
    assert not consent.covers(record, _capabilities(network_permissions=["b.test"])).covered  # pyright: ignore[reportArgumentType]


def test_a_corrupt_fingerprint_reads_as_empty_rather_than_raising(
    registry: sqlite3.Connection,
) -> None:
    consent.grant(
        registry,
        consent_id="request_01J0000000000000000000000Z",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint=consent.fingerprint_of({}),
        decided_by=OWNER,
        origin="registry search",
        at=MOMENT,
    )
    registry.execute("UPDATE consent SET fingerprint = '\"not an object\"'")

    # An empty fingerprint is the safe reading: every candidate then looks like
    # an expansion and the user is asked again, which is the direction to fail.
    found = consent.held(registry, scope=consent.SCOPE_PUBLISHER, target="publisher/acme")
    assert found is not None and found.fingerprint == {}
    assert not consent.covers(found, _capabilities(network_permissions=["a.test"])).covered  # pyright: ignore[reportArgumentType]


# --- migration and concurrency --------------------------------------------


@pytest.mark.parametrize("from_version", [1, 2, 3])
def test_a_representative_database_of_an_older_schema_migrates(
    tmp_path: Path, from_version: int
) -> None:
    """`#159`: migration proved on a database that actually holds rows.

    An empty database migrates trivially and proves nothing about a migration
    that has to preserve data. Each of these is built at its own version, filled
    with what that version could hold, and then brought forward.
    """
    place = tmp_path / f"registry-v{from_version}.sqlite3"
    with closing(open_registry(place, create=True)) as connection:
        database.downgrade(connection, from_version)
        assert database.schema_version(connection) == from_version
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
            ("component_01J00000000000000000000010", MOMENT),
        )
        connection.commit()

    with closing(open_registry(place, create=False)) as migrated:
        assert database.schema_version(migrated) == database.SCHEMA_VERSION
        held = migrated.execute("SELECT COUNT(*) AS n FROM entity").fetchone()
        assert held["n"] == 1
        # And the new tables are usable on a database that predates them.
        stored = content.put(migrated, b"after migration", at=MOMENT)
        assert content.get(migrated, stored.digest) == b"after migration"


def test_two_processes_storing_the_same_bytes_agree(tmp_path: Path) -> None:
    place = tmp_path / "shared.sqlite3"
    with closing(open_registry(place, create=True)):
        pass

    digests: list[str] = []
    failures: list[BaseException] = []

    def store() -> None:
        try:
            with closing(open_registry(place, create=False)) as connection:
                digests.append(content.put(connection, b"contended", at=MOMENT).digest)
                connection.commit()
        except BaseException as error:  # pragma: no cover - only on a real race failure
            failures.append(error)

    workers = [threading.Thread(target=store) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert not failures
    # Eight writers, one address, one row. Deduplication is the primary key's
    # job, so contention cannot produce a second copy.
    assert set(digests) == {content.address_of(b"contended")}
    with closing(open_registry(place, create=False)) as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM content").fetchone()["n"] == 1


def test_two_processes_entombing_one_entity_agree_on_one_mark(tmp_path: Path) -> None:
    place = tmp_path / "raced.sqlite3"
    held = "component_01J00000000000000000000011"
    with closing(open_registry(place, create=True)) as connection:
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
            (held, MOMENT),
        )
        connection.commit()

    marks: list[lifecycle.Tombstone] = []
    failures: list[BaseException] = []

    def entomb(moment: str) -> None:
        try:
            with closing(open_registry(place, create=False)) as connection:
                marks.append(lifecycle.entomb(connection, held, reason="raced", at=moment))
                connection.commit()
        except BaseException as error:  # pragma: no cover - only on a real race failure
            failures.append(error)

    workers = [threading.Thread(target=entomb, args=(m,)) for m in (MOMENT, LATER, MOMENT, LATER)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert not failures
    assert len({mark.created_at for mark in marks}) == 1
    with closing(open_registry(place, create=False)) as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM tombstone").fetchone()["n"] == 1


@pytest.mark.parametrize("field", consent.FINGERPRINT_FIELDS)
def test_growth_in_any_declared_field_revokes_coverage(field: str) -> None:
    """`#168`: a new major, a new permission, network **and path** all invalidate.

    Parametrised over the whole field list rather than over the two or three a
    hand-written test would reach for. `managed_paths` is named in the acceptance
    criteria and was the one nothing exercised — and a fingerprint field that no
    test compares is a field that could quietly stop being compared.
    """
    record = consent.Record(
        consent_id="request_01J00000000000000000000080",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint=consent.fingerprint_of({}),
        decided_by=OWNER,
        origin="registry search",
        created_at=MOMENT,
        revoked_at=None,
    )
    verdict = consent.covers(record, {field: ["something-new"]})
    assert not verdict.covered
    assert verdict.changed == (field,)
    assert "more than when consent was given" in verdict.reason


def test_a_consent_records_the_actor_the_moment_and_where_it_was_given(
    registry: sqlite3.Connection,
) -> None:
    """`#168` asks for actor, time and capability fingerprint on every record."""
    record = consent.grant(
        registry,
        consent_id="request_01J00000000000000000000081",
        scope=consent.SCOPE_OBJECT_MAJOR,
        target="component_01J00000000000000000000082@1",
        fingerprint=consent.fingerprint_of({"network_permissions": ["a.test"]}),
        decided_by=OWNER,
        origin="registry show",
        at=MOMENT,
    )
    assert record.decided_by == OWNER
    assert record.created_at == MOMENT
    assert record.origin == "registry show"
    assert set(record.fingerprint) == set(consent.FINGERPRINT_FIELDS)
