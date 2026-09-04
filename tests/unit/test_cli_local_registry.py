"""The local registry: durable, migrated, content-addressed, read-only on reads."""

import os
import sqlite3
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import journal, passports, revisions
from ai_stp_cli.local.database import (
    BUSY_TIMEOUT_MILLISECONDS,
    MIGRATIONS,
    SCHEMA_VERSION,
    configured_path,
    downgrade,
    file_schema_version,
    open_readonly,
    open_registry,
    schema_version,
    transaction,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp, is_valid_timestamp

DEVICE = "device_01KZAA000000000000000000A0"

# POSIX st_mode bits are not meaningful access control on Windows (ACLs govern).
_POSIX = os.name != "nt"


@pytest.fixture
def registry(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        yield connection
    finally:
        connection.close()


def _content(stable_id: str, owner: str, at: str, **extra: JsonValue) -> dict[str, JsonValue]:
    document: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "developer",
        "stable_id": stable_id,
        "owner_id": owner,
        "created_at": at,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {},
    }
    document.update(extra)
    return document


def test_a_clean_home_opens_at_the_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "registry.sqlite"
    connection = open_registry(path)
    assert schema_version(connection) == SCHEMA_VERSION
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    connection.close()


def test_reopening_is_deterministic_and_applies_nothing_twice(tmp_path: Path) -> None:
    path = tmp_path / "registry.sqlite"
    first = open_registry(path)
    tables = sorted(
        str(row[0]) for row in first.execute("SELECT name FROM sqlite_master WHERE type='table'")
    )
    first.close()

    second = open_registry(path)
    assert schema_version(second) == SCHEMA_VERSION
    assert (
        sorted(
            str(row[0])
            for row in second.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
        == tables
    )
    second.close()


def test_the_database_and_its_journal_are_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "registry.sqlite"
    connection = open_registry(path)
    with transaction(connection):
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) "
            "VALUES ('developer_x', 'developer', 'now')"
        )
    assert path.exists()
    for candidate in (path, Path(f"{path}-wal")):
        if candidate.exists() and _POSIX:
            # POSIX-only: Windows st_mode is not 0o600 even when the file is protected.
            # WAL writes the same rows as the database; a permissive journal
            # would publish what the database itself protects.
            assert stat.S_IMODE(candidate.stat().st_mode) == 0o600, candidate.name
    connection.close()


def test_foreign_keys_are_enforced(registry: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError), transaction(registry):
        registry.execute(
            "INSERT INTO revision "
            "(revision_id, stable_id, content, device_id, created_at) "
            "VALUES ('revision_x', 'developer_missing', '{}', ?, 'now')",
            (DEVICE,),
        )


def test_a_failed_transaction_leaves_nothing_behind(registry: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError), transaction(registry):
        registry.execute(
            "INSERT INTO entity (stable_id, kind, created_at) "
            "VALUES ('developer_x', 'developer', 'now')"
        )
        raise RuntimeError("interrupted")
    assert registry.execute("SELECT COUNT(*) FROM entity").fetchone()[0] == 0


def test_migrations_roll_back_where_a_reverse_is_declared(tmp_path: Path) -> None:
    connection = open_registry(tmp_path / "registry.sqlite")
    downgrade(connection, 0)
    assert schema_version(connection) == 0
    assert (
        connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        == 0
    )
    connection.close()


def test_event_order_migration_materializes_existing_insertion_order(tmp_path: Path) -> None:
    path = tmp_path / "registry.sqlite"
    connection = open_registry(path)
    downgrade(connection, 14)
    with transaction(connection):
        for number in (1, 2):
            operation_id = f"operation_legacy_{number}"
            connection.execute(
                "INSERT INTO operation (operation_id, kind, state, started_at) "
                "VALUES (?, 'legacy', 'verified', '2026-08-08T10:00:00.000Z')",
                (operation_id,),
            )
            connection.execute(
                "INSERT INTO operation_event "
                "(operation_id, sequence, at, state_before, state_after, result, evidence) "
                "VALUES (?, 1, '2026-08-08T10:00:00.000Z', 'applying', "
                "'verified', 'legacy', NULL)",
                (operation_id,),
            )
    connection.close()

    upgraded = open_registry(path)
    rows = upgraded.execute(
        "SELECT operation_id, global_sequence FROM operation_event ORDER BY global_sequence"
    ).fetchall()
    assert [(str(row["operation_id"]), int(row["global_sequence"])) for row in rows] == [
        ("operation_legacy_1", 1),
        ("operation_legacy_2", 2),
    ]
    upgraded.close()


def test_a_migration_without_a_reverse_refuses_rather_than_guessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.local import database

    connection = open_registry(tmp_path / "registry.sqlite")
    stripped = tuple(
        migration.__class__(migration.version, migration.summary, migration.up)
        for migration in MIGRATIONS
    )
    monkeypatch.setattr(database, "MIGRATIONS", stripped)
    with pytest.raises(CliFailure, match="declares no reverse") as raised:
        downgrade(connection, 0)
    assert raised.value.code == "AI_STP_UNSUPPORTED_APPLY"
    connection.close()


def test_a_newer_schema_is_refused_and_the_file_is_left_intact(tmp_path: Path) -> None:
    # The one way to lose data is to open a file a newer build wrote and
    # downgrade it silently.
    path = tmp_path / "registry.sqlite"
    connection = open_registry(path)
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION + 5}")
    connection.close()
    before = path.read_bytes()

    with pytest.raises(CliFailure, match="newer build") as raised:
        open_registry(path)
    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"
    assert path.read_bytes() == before
    assert file_schema_version(path) == SCHEMA_VERSION + 5


def test_reading_the_schema_version_does_not_migrate(tmp_path: Path) -> None:
    # `doctor` must be able to look without upgrading: it is declared `read`.
    path = tmp_path / "registry.sqlite"
    open_registry(path).close()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version=0")
    connection.close()
    assert file_schema_version(path) == 0
    assert file_schema_version(path) == 0


def test_a_missing_registry_is_a_typed_answer_when_creation_is_not_asked_for(
    tmp_path: Path,
) -> None:
    with pytest.raises(CliFailure, match="does not exist yet") as raised:
        open_registry(tmp_path / "absent.sqlite", create=False)
    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert not (tmp_path / "absent.sqlite").exists()


def test_readonly_open_of_a_missing_registry_is_typed_and_creates_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "absent.sqlite"

    with pytest.raises(CliFailure, match="does not exist yet") as raised:
        open_readonly(path)

    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert not path.exists()


def test_identical_content_is_one_revision(registry: sqlite3.Connection) -> None:
    owner, developer = new_id("account"), new_id("developer")
    at = passports.moment()
    first = revisions.commit(registry, _content(developer, owner, at), device_id=DEVICE)
    again = revisions.commit(registry, _content(developer, owner, at), device_id=DEVICE)
    assert again.revision_id == first.revision_id
    assert registry.execute("SELECT COUNT(*) FROM revision").fetchone()[0] == 1
    assert len(revisions.heads(registry, developer)) == 1


def test_a_child_moves_the_head_and_keeps_the_history(registry: sqlite3.Connection) -> None:
    owner, developer = new_id("account"), new_id("developer")
    at = passports.moment()
    first = revisions.commit(registry, _content(developer, owner, at), device_id=DEVICE)
    second = revisions.commit(
        registry,
        _content(
            developer,
            owner,
            at,
            parent_revision_ids=[first.revision_id],
            facts={"role": {"value": "backend", "origin": "declared", "confirmation": "none"}},
        ),
        device_id=DEVICE,
    )
    current = revisions.head(registry, developer)
    assert current is not None
    assert current.revision_id == second.revision_id
    assert second.parents == (first.revision_id,)
    stored = registry.execute(
        "SELECT revision_id FROM revision WHERE stable_id = ? ORDER BY rowid", (developer,)
    ).fetchall()
    assert [str(row[0]) for row in stored] == [first.revision_id, second.revision_id]
    kind = registry.execute("SELECT kind FROM entity WHERE stable_id = ?", (developer,)).fetchone()
    assert str(kind[0]) == "developer"


# `SPEC-003` REQ-302: a passport has a stable id, a schema version and
# immutable revisions with parents.
def test_the_revision_id_describes_the_content_it_is_stored_under(
    registry: sqlite3.Connection,
) -> None:
    from ai_stp_passports.envelope import verify_revision_id

    owner, developer = new_id("account"), new_id("developer")
    stored = revisions.commit(
        registry, _content(developer, owner, passports.moment()), device_id=DEVICE
    )
    assert verify_revision_id(stored.envelope)
    assert stored.envelope.revision_id == stored.revision_id


@pytest.mark.parametrize("case", ["missing", "other_entity"])
def test_a_parent_outside_the_graph_is_refused(case: str, registry: sqlite3.Connection) -> None:
    owner = new_id("account")
    at = passports.moment()
    mine = new_id("developer")
    revisions.commit(registry, _content(mine, owner, at), device_id=DEVICE)

    if case == "missing":
        parent = "revision_" + "0" * 64
        expected = "not in the local registry"
    else:
        # A component rather than a second developer: schema 2 allows exactly
        # one developer passport per installation, so two of them can no longer
        # be constructed — which is the point of that constraint.
        other = new_id("component")
        parent = revisions.commit(
            registry, _content(other, owner, at, kind="component"), device_id=DEVICE
        ).revision_id
        expected = "belongs to a different object"

    with pytest.raises(CliFailure, match=expected):
        revisions.commit(
            registry,
            _content(mine, owner, at, parent_revision_ids=[parent], visibility="private"),
            device_id=DEVICE,
        )


def test_two_heads_are_reported_rather_than_silently_resolved(
    registry: sqlite3.Connection,
) -> None:
    # Divergence is representable, and picking one silently is what `SPEC-009`
    # REQ-906 forbids.
    owner, developer = new_id("account"), new_id("developer")
    at = passports.moment()
    root = revisions.commit(registry, _content(developer, owner, at), device_id=DEVICE)
    for role in ("backend", "frontend"):
        revisions.commit(
            registry,
            _content(
                developer,
                owner,
                at,
                parent_revision_ids=[root.revision_id],
                facts={"role": {"value": role, "origin": "declared", "confirmation": "none"}},
            ),
            device_id=DEVICE,
        )
    assert len(revisions.heads(registry, developer)) == 2
    with pytest.raises(CliFailure, match="more than one head") as raised:
        revisions.head(registry, developer)
    assert raised.value.code == "AI_STP_CONFLICT"


def test_revision_graph_finds_fast_forward_and_the_nearest_common_ancestor(
    registry: sqlite3.Connection,
) -> None:
    owner, developer = new_id("account"), new_id("developer")
    at = passports.moment()
    root = revisions.commit(registry, _content(developer, owner, at), device_id=DEVICE)
    left = revisions.commit(
        registry,
        _content(
            developer,
            owner,
            at,
            parent_revision_ids=[root.revision_id],
            facts={"left": {"value": True, "origin": "declared", "confirmation": "none"}},
        ),
        device_id=DEVICE,
    )
    right = revisions.commit(
        registry,
        _content(
            developer,
            owner,
            at,
            parent_revision_ids=[root.revision_id],
            facts={"right": {"value": True, "origin": "declared", "confirmation": "none"}},
        ),
        device_id="device_01KZAA000000000000000000B0",
    )

    assert revisions.is_ancestor(registry, root.revision_id, left.revision_id)
    assert not revisions.is_ancestor(registry, left.revision_id, right.revision_id)
    ancestor = revisions.common_ancestor(registry, left.revision_id, right.revision_id)
    assert ancestor is not None
    assert ancestor.revision_id == root.revision_id
    assert revisions.common_ancestor(registry, left.revision_id, left.revision_id) == left
    assert revisions.common_ancestor(registry, left.revision_id, "revision_" + "0" * 64) is None


def test_reads_never_write(registry: sqlite3.Connection) -> None:
    # `SPEC-009` REQ-902 stated as a comparison of the whole database before and
    # after every read this module offers.
    owner, developer = new_id("account"), new_id("developer")
    stored = revisions.commit(
        registry, _content(developer, owner, passports.moment()), device_id=DEVICE
    )
    registry.execute("PRAGMA wal_checkpoint(FULL)")
    before = list(registry.execute("SELECT * FROM revision").fetchall())

    revisions.get(registry, stored.revision_id)
    revisions.heads(registry, developer)
    revisions.head(registry, developer)
    passports.developer_stable_id(registry)
    passports.device_stable_id(registry)
    journal.unsettled(registry)

    assert list(registry.execute("SELECT * FROM revision").fetchall()) == before
    assert registry.execute("SELECT COUNT(*) FROM operation").fetchone()[0] == 0


def test_an_unknown_revision_reads_as_absent(registry: sqlite3.Connection) -> None:
    assert revisions.get(registry, "revision_" + "0" * 64) is None
    assert revisions.head(registry, new_id("developer")) is None


def test_the_journal_records_a_mutation_and_its_outcome(registry: sqlite3.Connection) -> None:
    at = passports.moment()
    operation_id = journal.begin(registry, "test.mutation", at)
    entry = journal.get(registry, operation_id)
    assert entry is not None
    assert entry.state == "applying"
    assert is_valid_timestamp(entry.started_at)
    # Unsettled is the diagnostic: this is what an interrupted run leaves.
    assert [item.operation_id for item in journal.unsettled(registry)] == [operation_id]

    journal.settle(registry, operation_id, "verified", passports.moment())
    settled = journal.get(registry, operation_id)
    assert settled is not None
    assert settled.state == "verified"
    assert settled.finished_at is not None
    assert journal.unsettled(registry) == ()


def test_an_interrupted_mutation_stays_visible_as_unsettled(registry: sqlite3.Connection) -> None:
    # The crash-before-commit shape: the effect may or may not have landed, and
    # the journal is what says which entries need looking at.
    stuck = journal.begin(registry, "test.interrupted", passports.moment())
    journal.settle(registry, stuck, "applied_unverified", passports.moment())
    assert [item.state for item in journal.unsettled(registry)] == ["applied_unverified"]
    assert journal.get(registry, stuck) is not None
    assert journal.get(registry, new_id("operation")) is None


def test_a_failed_mutation_settles_as_failed_and_writes_no_revision(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    passports.init_developer(registry, device_id=DEVICE)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk gone")

    monkeypatch.setattr(revisions, "commit", explode)
    with pytest.raises(RuntimeError):
        passports.update_developer(registry, {"role": "backend"}, device_id=DEVICE)

    assert list(journal.unsettled(registry)) == []
    entries = registry.execute("SELECT state FROM operation ORDER BY started_at").fetchall()
    assert [str(row[0]) for row in entries][-1] == "failed"


def test_the_created_at_of_a_migration_stamp_is_a_real_moment() -> None:
    from datetime import UTC, datetime

    assert is_valid_timestamp(format_timestamp(datetime.now(UTC)))


@pytest.mark.parametrize("document", ["{not json", '["a list"]', '{"account_id": "not-an-id"}'])
def test_a_damaged_owner_record_is_named_not_guessed(document: str) -> None:
    from ai_stp_cli.paths import data_dir, write_private

    passports.owner()
    write_private(data_dir() / "owner.json", document)
    with pytest.raises(CliFailure, match="owner record cannot be read"):
        passports.owner()


def test_the_owner_identity_is_minted_once_and_reused() -> None:
    # `ADR-0060`: one local owner per installation, stable until `#75` transfers
    # ownership to the account the server issues.
    first = passports.owner()
    assert first.account_id.startswith("account_")
    assert passports.owner().account_id == first.account_id


def test_known_owner_reads_without_minting() -> None:
    from ai_stp_cli.paths import data_dir

    assert passports.known_owner() is None
    assert not data_dir().exists()

    first = passports.owner()
    assert passports.known_owner() == first


def test_updating_without_a_passport_is_a_typed_answer(registry: sqlite3.Connection) -> None:
    with pytest.raises(CliFailure, match="no developer passport yet") as raised:
        passports.update_developer(registry, {"role": "backend"}, device_id=DEVICE)
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_failed_device_refresh_settles_the_journal(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk gone")

    monkeypatch.setattr(revisions, "commit", explode)
    with pytest.raises(RuntimeError):
        passports.ensure_device(registry, device_id=DEVICE)
    states = [str(row[0]) for row in registry.execute("SELECT state FROM operation")]
    assert states == ["failed"]


def test_a_migration_that_fails_leaves_the_version_where_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An interrupted upgrade must leave the file at its previous version rather
    # than half-way between two.
    from ai_stp_cli.local import database

    broken = (
        database.Migration(version=1, summary="broken", up=("CREATE TABLE ok (a TEXT)", "NOT SQL")),
    )
    monkeypatch.setattr(database, "MIGRATIONS", broken)
    path = tmp_path / "registry.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        database.open_registry(path)
    assert database.file_schema_version(path) == 0


def test_downgrading_past_what_is_applied_does_nothing(tmp_path: Path) -> None:
    connection = open_registry(tmp_path / "registry.sqlite")
    downgrade(connection, 0)
    downgrade(connection, 0)
    assert schema_version(connection) == 0
    connection.close()


def test_a_failed_developer_init_settles_the_journal(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk gone")

    monkeypatch.setattr(revisions, "commit", explode)
    with pytest.raises(RuntimeError):
        passports.init_developer(registry, device_id=DEVICE)
    assert [str(row[0]) for row in registry.execute("SELECT state FROM operation")] == ["failed"]


def test_a_registry_older_than_the_journal_shows_nothing_rather_than_failing(
    tmp_path: Path,
) -> None:
    # An older database simply has no journal table. That is not a fault to
    # report — the honest answer is that there is nothing to show.
    path = tmp_path / "registry.sqlite"
    open_registry(path).close()
    bare = sqlite3.connect(path)
    bare.execute("DROP TABLE operation")
    bare.commit()
    assert journal.unsettled(bare) == ()
    bare.close()


def test_a_second_passport_of_a_singleton_kind_is_refused(registry: sqlite3.Connection) -> None:
    """Schema 2 makes the constraint the storage layer's, not a convention.

    A lock keeps two local processes from racing, but it cannot cover a registry
    reached from another mount or handed over by a future sync. Before this, the
    lookups took the oldest row with `LIMIT 1`, so a second passport did not
    fail — it simply stopped being visible, and its revisions went with it.
    """
    owner, at = new_id("account"), passports.moment()
    revisions.commit(registry, _content(new_id("developer"), owner, at), device_id=DEVICE)

    with pytest.raises(CliFailure, match="already has a different passport of that kind") as raised:
        revisions.commit(registry, _content(new_id("developer"), owner, at), device_id=DEVICE)
    assert raised.value.code == "AI_STP_CONFLICT"
    assert raised.value.details["kind"] == "developer"

    counted = registry.execute("SELECT COUNT(*) FROM entity WHERE kind = 'developer'").fetchone()
    assert counted[0] == 1


def test_two_threads_opening_a_clean_registry_both_succeed(tmp_path: Path) -> None:
    """The loser of a concurrent first run must find the work done, not redo it.

    The schema version is read before the migration transaction begins, so
    another opener can finish the same migration in between. Without asking
    again under the write lock, the loser re-runs `CREATE TABLE` on tables that
    now exist and crashes — which is how six concurrent first runs failed.

    **Observed failing once, on `windows-latest`, 2026-08-28** (`33218639098`):
    `sqlite3.OperationalError: database is locked` from `BEGIN IMMEDIATE`, one
    failure in the last twelve `check` runs and none on the two other operating
    systems. `BUSY_TIMEOUT_MILLISECONDS` is 5000; a clean open measured here
    takes **33 ms** across five runs of all 23 migrations, so the budget is
    roughly 150x the work and raising it would be a round number against no
    measurement. What exceeded it was the runner, not the migration chain.

    **Recurred on `windows-latest`, 2026-09-02** (`33651558201`), on a branch
    whose only changes were Markdown — so the trigger is the runner, as the
    first occurrence concluded, and not a code path. Two occurrences in six
    days, both Windows, none elsewhere.

    **Recurred a third time on 2026-09-03** (run 33790300140) after migration
    29. The measured opens took 6439 ms and 6041 ms, exceeding the 5000 ms
    budget under a heavily loaded runner. The budget is now 15000 ms: more
    than twice the measured maximum, still bounded, and tied to this
    observation rather than an unexplained round-number increase.
    """
    import concurrent.futures
    import threading
    import time

    path = tmp_path / "registry.sqlite"
    ready = threading.Barrier(2)

    def open_it(_index: int) -> tuple[int | None, str | None, float]:
        ready.wait(timeout=10)
        started = time.perf_counter()
        try:
            connection = open_registry(path)
            try:
                version = schema_version(connection)
            finally:
                connection.close()
        except Exception as error:
            return None, f"{type(error).__name__}: {error}", time.perf_counter() - started
        return version, None, time.perf_counter() - started

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(open_it, range(2)))

    # The number the docstring asks for on a recurrence, carried by the run
    # that recurs rather than reconstructed afterwards. `pytest` prints this
    # only when the assertion below fails, so a green run stays silent.
    versions = [version for version, _error, _elapsed in outcomes]
    failures = [error for _version, error, _elapsed in outcomes if error is not None]
    held = sorted((elapsed for _version, _error, elapsed in outcomes), reverse=True)
    spent = ", ".join(f"{value * 1000:.0f} ms" for value in held)
    assert versions == [SCHEMA_VERSION, SCHEMA_VERSION], (
        f"opens took {spent} against a {BUSY_TIMEOUT_MILLISECONDS} ms budget; failures: {failures}"
    )


def test_an_owner_minted_by_another_process_is_adopted_not_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two first runs must not mint two owners.

    Every passport carries the owner inside its content, so a split here splits
    the whole local history. The loser re-reads under the lock and takes what it
    finds; planting the record while the lock is held stands in for that.
    """
    import json
    from collections.abc import Generator
    from contextlib import contextmanager

    from ai_stp_cli import paths as paths_module

    established = "account_01KZAA000000000000000000A0"
    real_lock = paths_module.bootstrap_lock

    @contextmanager
    def lock_then_plant(*_args: object, **_kwargs: object) -> Generator[None]:
        with real_lock():
            record = paths_module.data_dir() / "owner.json"
            if not record.exists():
                paths_module.write_private(record, json.dumps({"account_id": established}))
            yield

    monkeypatch.setattr(passports, "bootstrap_lock", lock_then_plant)
    assert passports.owner().account_id == established


def test_replaying_an_ancestor_does_not_fork_the_entity(registry: sqlite3.Connection) -> None:
    """A sync, an import or a recovery hands back revisions already held.

    Head movement used to run on the replay path too, so an ancestor was added
    back beside the current head. The entity then had two heads and `head()`
    refused it as a conflict with no concurrent edit anywhere — which would have
    made sync unimplementable on top of this.
    """
    owner, developer = new_id("account"), new_id("developer")
    at = passports.moment()
    root_content = _content(developer, owner, at)
    root = revisions.commit(registry, root_content, device_id=DEVICE)
    child = revisions.commit(
        registry,
        _content(
            developer,
            owner,
            at,
            parent_revision_ids=[root.revision_id],
            facts={"role": {"value": "backend", "origin": "declared", "confirmation": "none"}},
        ),
        device_id=DEVICE,
    )

    replayed = revisions.commit(registry, root_content, device_id=DEVICE)

    assert replayed.revision_id == root.revision_id
    heads = revisions.heads(registry, developer)
    assert [item.revision_id for item in heads] == [child.revision_id]
    assert registry.execute("SELECT COUNT(*) FROM revision").fetchone()[0] == 2


def test_replaying_the_current_head_is_a_no_op(registry: sqlite3.Connection) -> None:
    owner, developer = new_id("account"), new_id("developer")
    at = passports.moment()
    content = _content(developer, owner, at)
    first = revisions.commit(registry, content, device_id=DEVICE)

    again = revisions.commit(registry, content, device_id="device_01KZAA00000000000000000ZZZ")

    assert again.revision_id == first.revision_id
    # How a revision came to exist is a column, not content: the first writer is
    # the one that recorded it, and a replay does not rewrite that.
    assert again.device_id == DEVICE
    assert [item.revision_id for item in revisions.heads(registry, developer)] == [
        first.revision_id
    ]


def test_a_lost_race_to_enable_write_ahead_logging_is_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two openers set the same mode, so losing to the other one is harmless.

    Changing the journal mode takes a brief exclusive lock and SQLite does not
    reliably apply the busy handler to that statement, so a concurrent first run
    can be refused outright. Retried rather than checked once: the winner may
    hold the lock without having committed the change yet, and asking again
    immediately is how the first version of this lost the race it was written
    for. A refusal that never resolves still raises.
    """
    from ai_stp_cli.local import database

    monkeypatch.setattr(database, "MODE_SWITCH_SECONDS", 0.1)

    class Opener:
        """Refuses the switch, and reports the mode from `answers` in turn."""

        def __init__(self, *answers: str) -> None:
            self.answers = list(answers)
            self.attempts = 0

        def execute(self, statement: str) -> "Opener":
            if statement == "PRAGMA journal_mode=WAL":
                self.attempts += 1
                raise sqlite3.OperationalError("database is locked")
            return self

        def fetchone(self) -> tuple[str]:
            return (self.answers.pop(0) if len(self.answers) > 1 else self.answers[0],)

    # The winner committed the change while this one was retrying.
    lost = Opener("delete", "wal")
    database.enable_write_ahead_logging(lost)  # pyright: ignore[reportArgumentType]
    assert lost.attempts == 1

    # Nobody ever set it, so the refusal is real and outlives the deadline.
    stuck = Opener("delete")
    with pytest.raises(sqlite3.OperationalError):
        database.enable_write_ahead_logging(stuck)  # pyright: ignore[reportArgumentType]
    assert stuck.attempts > 1, "the switch was not retried"

    # Already in the right mode: not attempted at all.
    settled = Opener("wal")
    database.enable_write_ahead_logging(settled)  # pyright: ignore[reportArgumentType]
    assert settled.attempts == 0


def test_two_openers_racing_the_same_migration_leave_one_applied(tmp_path: Path) -> None:
    """The loser re-checks under the write lock and finds the work already done.

    The version is read before the migration transaction opens, so a concurrent
    opener can finish the same step in between. Re-running it would try to
    create tables that exist and crash the second process — which is how six
    concurrent first runs failed.
    """
    from ai_stp_cli.local import database

    path = tmp_path / "registry.sqlite"
    open_registry(path).close()

    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        # Exactly the loser's position: about to apply a migration the file
        # already carries.
        database._run(  # pyright: ignore[reportPrivateUsage]
            connection, MIGRATIONS[0].up, 1, skip_if_reached=1
        )
        assert database.schema_version(connection) == SCHEMA_VERSION
    finally:
        connection.close()


# The transition guard: a state that can move anywhere records nothing.
def test_an_operation_cannot_move_to_a_state_nothing_allows(
    registry: sqlite3.Connection,
) -> None:
    operation_id = journal.begin(registry, "test.kind", passports.moment())
    journal.settle(registry, operation_id, "verified", passports.moment())

    with pytest.raises(CliFailure) as raised:
        journal.settle(registry, operation_id, "applying", passports.moment())
    assert raised.value.code == "AI_STP_CONFLICT"
    assert raised.value.details["from"] == "verified"


def test_settling_an_operation_that_does_not_exist_is_not_found(
    registry: sqlite3.Connection,
) -> None:
    with pytest.raises(CliFailure) as raised:
        journal.settle(
            registry, "operation_01J0000000000000000000000Z", "verified", passports.moment()
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_settling_to_the_state_it_already_holds_is_allowed(
    registry: sqlite3.Connection,
) -> None:
    """A replay of the same outcome is not a transition and must not fail."""
    operation_id = journal.begin(registry, "test.kind", passports.moment())
    journal.settle(registry, operation_id, "failed", passports.moment(), "first")
    journal.settle(registry, operation_id, "failed", passports.moment(), "again")
    held = journal.get(registry, operation_id)
    assert held is not None and held.state == "failed"


def test_a_terminal_state_allows_nothing() -> None:
    """An operation that can leave its outcome never really had one."""
    for state in ("verified", "failed", "partial", "stale", "cancelled", "rolled_back"):
        assert journal.TRANSITIONS[state] == frozenset()


def test_partial_is_an_outcome_that_still_needs_a_person() -> None:
    """It is terminal, and deliberately not `settled`: it must stay visible."""
    assert journal.TRANSITIONS["partial"] == frozenset()
    assert "partial" not in journal.SETTLED


def test_cancelling_is_impossible_once_an_effect_may_have_happened() -> None:
    """Cancelling claims nothing was done; after `applying` nobody can claim it."""
    assert "cancelled" in journal.TRANSITIONS["approved"]
    assert "cancelled" not in journal.TRANSITIONS["applying"]
    assert "cancelled" not in journal.TRANSITIONS["applied_unverified"]


def test_every_declared_state_has_a_row_in_the_table() -> None:
    """A state with no row allows nothing by accident rather than by decision."""
    from typing import get_args

    declared = set(get_args(journal.OperationState.__value__))
    assert set(journal.TRANSITIONS) == declared
    assert declared >= journal.SETTLED


def test_an_unknown_state_allows_nothing() -> None:
    assert not journal.allowed("invented", "verified")
    assert not journal.allowed("verified", "invented")


@pytest.mark.unprivileged
def test_a_wal_registry_in_an_unwritable_directory_still_answers_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`open_readonly` must not need to write the directory it reads from.

    Measured across the read surface: `component find`, `target status`,
    `install status`, `select eligibility-matrix` and `harness status` all
    answered `AI_STP_INTERNAL` against a data directory without write
    permission. `open_registry` had left the database in WAL mode; a read-only
    connection then has to create the `-shm` index beside it, and the
    directory refused. The passive-check test never caught it because a fresh
    check answers without any registry at all. With no `-wal` present and the
    directory unwritable no writer can start a WAL session, so falling back to
    an immutable open changes nothing about what the reader can observe.
    """
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    (home / "config").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    place = configured_path()
    connection = open_registry(place, create=True)
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES ('component_x', 'component', 't')"
    )
    connection.commit()
    connection.close()

    place.parent.chmod(0o500)
    try:
        held = open_readonly(place)
        try:
            count = held.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        finally:
            held.close()
    finally:
        place.parent.chmod(0o700)

    assert count == 1
