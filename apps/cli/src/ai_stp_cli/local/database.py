"""The local registry file: opening it, and moving its schema forward.

`SPEC-009` REQ-901 asks for migrations, write-ahead logging, foreign keys,
transactions and restrictive file permissions. All five are here and none of
them needs a dependency: `ADR-0059` records why the stated Alembic was measured
and declined — it arrives through SQLAlchemy, costs about half a second of
import on the first command that opens the registry, and adds fifteen megabytes
to a wheel for a metadata store with four tables.

The schema version lives in `PRAGMA user_version`, which SQLite stores in the
file header. Migrations are an ordered list applied inside one transaction each,
so an interrupted upgrade leaves the file at its previous version rather than
half-way between two.
"""

import sqlite3
import time
from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import FILE_MODE, POSIX, ensure_directory, redact_home


@dataclass(frozen=True)
class Migration:
    """One step forward, and its reverse when the reverse is expressible."""

    version: int
    summary: str
    up: tuple[str, ...]

    #: Declared only where it is honest. Dropping a table reverses creating one;
    #: nothing reverses discarding rows, so such a migration declares no down
    #: step and `downgrade` refuses rather than pretending.
    down: tuple[str, ...] = ()


MIGRATIONS: Final[tuple[Migration, ...]] = (
    Migration(
        version=1,
        summary="entities, content-addressed revisions, heads and the operation journal",
        up=(
            """
            CREATE TABLE entity (
                stable_id  TEXT PRIMARY KEY,
                kind       TEXT NOT NULL,
                created_at TEXT NOT NULL
            ) STRICT
            """,
            """
            CREATE TABLE revision (
                revision_id  TEXT PRIMARY KEY,
                stable_id    TEXT NOT NULL REFERENCES entity(stable_id),
                content      TEXT NOT NULL,
                device_id    TEXT NOT NULL,
                operation_id TEXT,
                created_at   TEXT NOT NULL
            ) STRICT
            """,
            """
            CREATE TABLE revision_parent (
                revision_id        TEXT NOT NULL REFERENCES revision(revision_id),
                parent_revision_id TEXT NOT NULL REFERENCES revision(revision_id),
                PRIMARY KEY (revision_id, parent_revision_id)
            ) STRICT
            """,
            """
            CREATE TABLE head (
                stable_id   TEXT NOT NULL REFERENCES entity(stable_id),
                revision_id TEXT NOT NULL REFERENCES revision(revision_id),
                PRIMARY KEY (stable_id, revision_id)
            ) STRICT
            """,
            """
            CREATE TABLE operation (
                operation_id TEXT PRIMARY KEY,
                kind         TEXT NOT NULL,
                state        TEXT NOT NULL,
                started_at   TEXT NOT NULL,
                finished_at  TEXT,
                detail       TEXT
            ) STRICT
            """,
            "CREATE INDEX revision_by_entity ON revision(stable_id)",
        ),
        down=(
            "DROP INDEX revision_by_entity",
            "DROP TABLE operation",
            "DROP TABLE head",
            "DROP TABLE revision_parent",
            "DROP TABLE revision",
            "DROP TABLE entity",
        ),
    ),
    Migration(
        version=2,
        summary="one developer and one device passport per installation, enforced by the schema",
        up=(
            # An installation has exactly one of each of these. Before this, two
            # concurrent first runs could each create one, and the lookups take
            # the oldest with `LIMIT 1` — so the second passport did not fail,
            # it simply stopped being visible, taking its revisions with it.
            #
            # A lock keeps two processes from starting the race; a constraint
            # decides it. Both exist because the lock cannot cover a registry
            # opened from another machine, another mount or a future sync.
            """
            CREATE UNIQUE INDEX one_passport_per_singleton_kind
            ON entity (kind) WHERE kind IN ('developer', 'device')
            """,
        ),
        down=("DROP INDEX one_passport_per_singleton_kind",),
    ),
    Migration(
        version=3,
        summary="a project passport is found again by the root it describes",
        up=(
            # A stable id is a ULID: it cannot be derived from a path, so the
            # only way a re-scan can preserve it is to look the project up by
            # something it already knows. That something is the root.
            #
            # Its own table rather than a column on `entity`, because it applies
            # to exactly one kind and a nullable column on the others would make
            # "no root" and "not a project" the same absent value.
            """
            CREATE TABLE project_root (
                root      TEXT PRIMARY KEY,
                stable_id TEXT NOT NULL UNIQUE REFERENCES entity(stable_id)
            ) STRICT
            """,
        ),
        down=("DROP TABLE project_root",),
    ),
    Migration(
        version=4,
        summary="content-addressed bytes, overlay provenance, consent records and tombstones",
        up=(
            # Bytes, named by their digest. The name *is* the integrity proof, so
            # a lookup cannot be satisfied by different content, and storing the
            # same bytes twice is refused by the primary key rather than by a
            # check somebody has to remember to write.
            #
            # `BLOB`, not `TEXT`: a component's bytes are whatever the author
            # wrote, and SQLite's `TEXT` asserts UTF-8 it cannot enforce here.
            """
            CREATE TABLE content (
                digest      TEXT PRIMARY KEY,
                bytes       BLOB NOT NULL,
                byte_length INTEGER NOT NULL,
                stored_at   TEXT NOT NULL
            ) STRICT
            """,
            # Where an overlay came from, kept beside the revision it produced.
            # `SPEC-005` REQ-506 makes a materialised overlay a composition
            # change, so the provenance has to survive as long as the version
            # does — recomputing it later would be guessing.
            """
            CREATE TABLE overlay_origin (
                revision_id TEXT PRIMARY KEY REFERENCES revision(revision_id),
                source_kind TEXT NOT NULL,
                source_ref  TEXT NOT NULL,
                base_digest TEXT NOT NULL,
                applied_at  TEXT NOT NULL
            ) STRICT
            """,
            # A durable consent record (`docs/contracts/unverified-consent.md`).
            # The capability fingerprint is stored, not derived on read: the
            # whole mechanism is "does the candidate now need more than it did
            # when the user agreed", and that question needs the old answer.
            #
            # `UNIQUE(scope, target)` because the contract has exactly two
            # scopes and one record each; a second record for one target would
            # make "which fingerprint applies" ambiguous.
            """
            CREATE TABLE consent (
                consent_id  TEXT PRIMARY KEY,
                scope       TEXT NOT NULL,
                target      TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                decided_by  TEXT NOT NULL,
                origin      TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                revoked_at  TEXT,
                UNIQUE (scope, target)
            ) STRICT
            """,
            # A tombstone marks an entity deleted (`SPEC-013` REQ-1308) without
            # removing its revisions: the sync contract replays a `tombstone`
            # operation, and replay has to be idempotent, so the mark is a row
            # keyed by the entity rather than a destructive delete.
            """
            CREATE TABLE tombstone (
                stable_id  TEXT PRIMARY KEY REFERENCES entity(stable_id),
                reason     TEXT NOT NULL,
                created_at TEXT NOT NULL
            ) STRICT
            """,
            "CREATE INDEX consent_by_target ON consent(target)",
        ),
        down=(
            "DROP INDEX consent_by_target",
            "DROP TABLE tombstone",
            "DROP TABLE consent",
            "DROP TABLE overlay_origin",
            "DROP TABLE content",
        ),
    ),
    Migration(
        version=5,
        summary="immutable X.Y versions and recorded fork provenance",
        up=(
            # `SPEC-005` REQ-504: one number cannot be reused for another hash.
            # The primary key is `(stable_id, version)` and the digest is an
            # ordinary column, so a second row for one number is refused by the
            # schema — a check in code would have to run on every path that
            # writes, and one of them would eventually not.
            """
            CREATE TABLE object_version (
                stable_id       TEXT NOT NULL REFERENCES entity(stable_id),
                version         TEXT NOT NULL,
                major           INTEGER NOT NULL,
                minor           INTEGER NOT NULL,
                passport_digest TEXT NOT NULL,
                revision_id     TEXT NOT NULL REFERENCES revision(revision_id),
                created_at      TEXT NOT NULL,
                PRIMARY KEY (stable_id, version)
            ) STRICT
            """,
            # Where a fork came from. REQ-521 leaves the original untouched, so
            # the link lives on the copy: writing it on the original would be a
            # change to something a recipient does not own.
            """
            CREATE TABLE fork_origin (
                stable_id        TEXT PRIMARY KEY REFERENCES entity(stable_id),
                source_stable_id TEXT NOT NULL,
                source_version   TEXT NOT NULL,
                source_digest    TEXT NOT NULL,
                created_at       TEXT NOT NULL
            ) STRICT
            """,
            "CREATE INDEX version_by_line ON object_version(stable_id, major, minor)",
        ),
        down=(
            "DROP INDEX version_by_line",
            "DROP TABLE fork_origin",
            "DROP TABLE object_version",
        ),
    ),
    Migration(
        version=6,
        summary="ephemeral composition proposals, recommendation traces and the selected version",
        up=(
            # A proposal is derived and short-lived (`REQ-622`), and the only
            # reason it touches disk at all is that proposing and confirming are
            # two processes. It is deliberately *not* a registry record: no
            # `entity` row, no revision, no head, so nothing here makes an
            # object exist. `ADR-0027` is explicit that showing a proposal must
            # stay distinguishable from creating one.
            #
            # The row outlives its own confirmation rather than being deleted by
            # it: `REQ-624` makes a repeated confirmation return the version
            # already created, and a record that vanished on success would
            # answer "unknown proposal" instead.
            """
            CREATE TABLE proposal (
                proposal_id         TEXT PRIMARY KEY,
                project_id          TEXT NOT NULL REFERENCES entity(stable_id),
                harness_id          TEXT NOT NULL,
                snapshot            TEXT NOT NULL,
                graph               TEXT NOT NULL,
                created_at          TEXT NOT NULL,
                expires_at          TEXT NOT NULL,
                cancelled_at        TEXT,
                confirmed_stable_id TEXT,
                confirmed_version   TEXT
            ) STRICT
            """,
            # `REQ-616`: the lane of every candidate, the state of its author and
            # version, the source of consent and the evidence. Written in the
            # same transaction as the version it explains, because a decision
            # without its reasons is the thing this table exists to prevent.
            #
            # Keyed by the version it explains rather than by an identifier of
            # its own. One version has one trace, and a separate key would make
            # a second trace for the same version expressible — a state where
            # the reasons behind a decision are ambiguous.
            """
            CREATE TABLE recommendation_trace (
                stable_id   TEXT NOT NULL REFERENCES entity(stable_id),
                version     TEXT NOT NULL,
                proposal_id TEXT NOT NULL REFERENCES proposal(proposal_id),
                snapshot    TEXT NOT NULL,
                body        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (stable_id, version)
            ) STRICT
            """,
            # Selected and installed are different facts. This holds the first;
            # `pending_install` is the ordinary window between them and not a
            # drift, which `selection-proposal.md` states in as many words. One
            # row per project and harness: the primary key is what makes a
            # second active selection impossible rather than merely unlikely.
            """
            CREATE TABLE selected_version (
                project_id  TEXT NOT NULL REFERENCES entity(stable_id),
                harness_id  TEXT NOT NULL,
                stable_id   TEXT NOT NULL REFERENCES entity(stable_id),
                version     TEXT NOT NULL,
                state       TEXT NOT NULL,
                selected_at TEXT NOT NULL,
                PRIMARY KEY (project_id, harness_id)
            ) STRICT
            """,
            "CREATE INDEX proposal_by_pair ON proposal(project_id, harness_id)",
        ),
        down=(
            "DROP INDEX proposal_by_pair",
            "DROP TABLE selected_version",
            "DROP TABLE recommendation_trace",
            "DROP TABLE proposal",
        ),
    ),
    Migration(
        version=7,
        summary="immutable operation plans and the append-only event stream",
        up=(
            # The plan of `operation.md`: immutable, hashed, and separate from
            # the operation's state. A plan that could change would make the
            # digest an approval of something else by the time it was applied.
            #
            # `idempotency_key` is `UNIQUE` rather than checked only in code: an
            # active retry must return the existing operation, and two processes
            # racing a terminal-key handoff must converge on one replacement.
            # Terminal keys are archived under the same write lock; old plans
            # and their event streams remain present.
            """
            CREATE TABLE operation_plan (
                operation_id           TEXT PRIMARY KEY REFERENCES operation(operation_id),
                idempotency_key        TEXT NOT NULL UNIQUE,
                action                 TEXT NOT NULL,
                author                 TEXT NOT NULL,
                target_id              TEXT NOT NULL,
                expected_target_digest TEXT NOT NULL,
                provider_version       TEXT NOT NULL,
                effects                TEXT NOT NULL,
                confirmation           TEXT NOT NULL,
                recovery_action        TEXT NOT NULL,
                plan_digest            TEXT NOT NULL,
                expires_at             TEXT NOT NULL,
                created_at             TEXT NOT NULL,
                approved_digest        TEXT,
                backup_ref             TEXT
            ) STRICT
            """,
            # Append-only. `operation.md` asks every step for a sequence number,
            # a time, the state either side and a safe result; the primary key
            # is what makes the stream ordered rather than merely timestamped,
            # since two events in one millisecond are ordinary.
            #
            # No secrets and no private content: the whole point of a "safe
            # result" is that this table can be read by anyone diagnosing a
            # stopped operation.
            """
            CREATE TABLE operation_event (
                operation_id TEXT NOT NULL REFERENCES operation(operation_id),
                sequence     INTEGER NOT NULL,
                at           TEXT NOT NULL,
                state_before TEXT NOT NULL,
                state_after  TEXT NOT NULL,
                result       TEXT NOT NULL,
                evidence     TEXT,
                PRIMARY KEY (operation_id, sequence)
            ) STRICT
            """,
        ),
        down=(
            "DROP TABLE operation_event",
            "DROP TABLE operation_plan",
        ),
    ),
    Migration(
        version=8,
        summary="provider backup references, held apart from the setups they precede",
        up=(
            # `REQ-814`: a `BackupRef` and an imported setup are separate
            # objects. Its own table rather than a column on the setup, because
            # a column would make the backup part of the setup's identity — and
            # then deleting a backup would delete the identity of the thing it
            # was supposed to protect.
            #
            # `provider_ref` is a reference and never bytes. The provider owns
            # the backup; copying it here would give one recovery two owners,
            # and only one of them can actually restore.
            """
            CREATE TABLE backup_ref (
                backup_id    TEXT PRIMARY KEY,
                harness_id   TEXT NOT NULL,
                target_id    TEXT NOT NULL,
                provider_ref TEXT NOT NULL,
                created_at   TEXT NOT NULL
            ) STRICT
            """,
        ),
        down=("DROP TABLE backup_ref",),
    ),
    Migration(
        version=9,
        summary="a plan says which setup version it installs, and what the target became",
        up=(
            # Rollback has to restore "the exact previous verified version"
            # (`#177`), and until now nothing recorded *which* version an
            # operation installed: the plan carried the target and the effect
            # strings, and those are sentences written for a person. Deriving
            # the history from the operation log is the right shape — the log
            # already says what was verified on which target — but only once the
            # plan names the version.
            "ALTER TABLE operation_plan ADD COLUMN setup_stable_id TEXT",
            "ALTER TABLE operation_plan ADD COLUMN setup_version TEXT",
            # What the target became after a verified apply. `expected_target_digest`
            # is what it was *before*; local drift is the difference between this
            # and what the target reads now, and without both there is nothing to
            # compare against.
            "ALTER TABLE operation_plan ADD COLUMN verified_target_digest TEXT",
        ),
        # The reverse is expressible, so it is declared. `DROP COLUMN` arrived in
        # SQLite 3.35 and these three columns are plain — not indexed, not part
        # of a key — which is the case it supports. Every table here already
        # uses `STRICT`, which needs 3.37, so the floor is above the one this
        # needs and no build that can read this schema lacks the statement.
        down=(
            "ALTER TABLE operation_plan DROP COLUMN verified_target_digest",
            "ALTER TABLE operation_plan DROP COLUMN setup_version",
            "ALTER TABLE operation_plan DROP COLUMN setup_stable_id",
        ),
    ),
    Migration(
        version=10,
        summary="installation plans bind the selected provider protocol boundary",
        up=(
            # Existing plans predate protocol v2. NULL distinguishes their old
            # digest domain from a newly-created v1 plan that explicitly binds
            # version 1. Treating both as integer 1 would change the digest of
            # an already-approved plan during migration.
            "ALTER TABLE operation_plan ADD COLUMN provider_protocol_version INTEGER",
            "ALTER TABLE operation_plan ADD COLUMN provider_target TEXT",
            "ALTER TABLE operation_plan ADD COLUMN plan_schema_version INTEGER",
        ),
        down=(
            "ALTER TABLE operation_plan DROP COLUMN plan_schema_version",
            "ALTER TABLE operation_plan DROP COLUMN provider_target",
            "ALTER TABLE operation_plan DROP COLUMN provider_protocol_version",
        ),
    ),
    Migration(
        version=11,
        summary="durable provider release history and monotonic anti-rollback floor",
        up=(
            """
            CREATE TABLE verified_provider_release (
                provider_id    TEXT NOT NULL,
                sequence       INTEGER NOT NULL,
                artifact_digest TEXT NOT NULL,
                verified_at    TEXT NOT NULL,
                PRIMARY KEY (provider_id, sequence)
            ) STRICT
            """,
            """
            CREATE TABLE provider_release_floor (
                provider_id      TEXT PRIMARY KEY,
                minimum_sequence INTEGER NOT NULL,
                artifact_digest  TEXT NOT NULL,
                advanced_at      TEXT NOT NULL
            ) STRICT
            """,
        ),
        down=(
            "DROP TABLE provider_release_floor",
            "DROP TABLE verified_provider_release",
        ),
    ),
    Migration(
        version=12,
        summary="installation plans bind a canonically signed provider release manifest",
        up=("ALTER TABLE operation_plan ADD COLUMN provider_release_manifest TEXT",),
        down=("ALTER TABLE operation_plan DROP COLUMN provider_release_manifest",),
    ),
    Migration(
        version=13,
        summary="installation plans bind an explicit verified-release recovery decision",
        up=(
            "ALTER TABLE operation_plan ADD COLUMN "
            "provider_release_recovery INTEGER NOT NULL DEFAULT 0",
        ),
        down=("ALTER TABLE operation_plan DROP COLUMN provider_release_recovery",),
    ),
    Migration(
        version=14,
        summary="installation plans bind exact bundle bytes and the provider plan",
        up=(
            "ALTER TABLE operation_plan ADD COLUMN bundle_format TEXT",
            "ALTER TABLE operation_plan ADD COLUMN bundle_digest TEXT",
            "ALTER TABLE operation_plan ADD COLUMN bundle_artifact_digest TEXT",
            "ALTER TABLE operation_plan ADD COLUMN bundle_size INTEGER",
            "ALTER TABLE operation_plan ADD COLUMN provider_plan_digest TEXT",
        ),
        down=(
            "ALTER TABLE operation_plan DROP COLUMN provider_plan_digest",
            "ALTER TABLE operation_plan DROP COLUMN bundle_size",
            "ALTER TABLE operation_plan DROP COLUMN bundle_artifact_digest",
            "ALTER TABLE operation_plan DROP COLUMN bundle_digest",
            "ALTER TABLE operation_plan DROP COLUMN bundle_format",
        ),
    ),
    Migration(
        version=15,
        summary="operation events carry one durable global serialization order",
        up=(
            "ALTER TABLE operation_event ADD COLUMN global_sequence INTEGER",
            # Existing rowids reflect insertion order in this local table.
            # Materialize them once so later reads do not depend on an implicit
            # SQLite identifier that VACUUM may rewrite.
            "UPDATE operation_event SET global_sequence = rowid",
            "CREATE UNIQUE INDEX operation_event_global_sequence_uq "
            "ON operation_event(global_sequence)",
        ),
        down=(
            "DROP INDEX operation_event_global_sequence_uq",
            "ALTER TABLE operation_event DROP COLUMN global_sequence",
        ),
    ),
    Migration(
        version=16,
        summary="durable exact report previews and interrupted submission recovery",
        up=(
            """
            CREATE TABLE report_plan (
                plan_id          TEXT PRIMARY KEY,
                plan_digest      TEXT NOT NULL UNIQUE,
                request_json     TEXT NOT NULL,
                created_at       TEXT NOT NULL,
                submitted_case   TEXT
            ) STRICT
            """,
        ),
        down=("DROP TABLE report_plan",),
    ),
    Migration(
        version=17,
        summary="durable sync event replay, remote revision mapping and account cursor",
        up=(
            """
            CREATE TABLE sync_event (
                account_id         TEXT NOT NULL,
                event_id           TEXT NOT NULL,
                sync_key           TEXT NOT NULL,
                local_revision_id  TEXT,
                remote_revision_id TEXT NOT NULL,
                entity_id          TEXT NOT NULL,
                direction          TEXT NOT NULL,
                request_json       TEXT NOT NULL,
                state              TEXT NOT NULL,
                receipt_json       TEXT,
                created_at         TEXT NOT NULL,
                PRIMARY KEY (account_id, event_id),
                UNIQUE (account_id, remote_revision_id)
            ) STRICT
            """,
            "CREATE UNIQUE INDEX sync_push_by_key ON sync_event"
            "(account_id, sync_key) WHERE direction = 'push'",
            """
            CREATE TABLE sync_remote_head (
                account_id         TEXT NOT NULL,
                entity_id          TEXT NOT NULL,
                remote_revision_id TEXT NOT NULL,
                PRIMARY KEY (account_id, entity_id)
            ) STRICT
            """,
            """
            CREATE TABLE sync_cursor (
                account_id TEXT PRIMARY KEY,
                cursor     TEXT,
                updated_at TEXT NOT NULL
            ) STRICT
            """,
        ),
        down=(
            "DROP TABLE sync_cursor",
            "DROP TABLE sync_remote_head",
            "DROP INDEX sync_push_by_key",
            "DROP TABLE sync_event",
        ),
    ),
    Migration(
        version=18,
        summary="content-addressed setup evaluation plans and immutable local results",
        up=(
            """
            CREATE TABLE eval_plan (
                plan_id       TEXT PRIMARY KEY,
                plan_digest   TEXT NOT NULL UNIQUE,
                document_json TEXT NOT NULL,
                created_at    TEXT NOT NULL
            ) STRICT
            """,
            """
            CREATE TABLE eval_result (
                run_id         TEXT PRIMARY KEY,
                plan_id        TEXT NOT NULL UNIQUE REFERENCES eval_plan(plan_id),
                result_digest  TEXT NOT NULL UNIQUE,
                document_json  TEXT NOT NULL,
                executed_at    TEXT NOT NULL
            ) STRICT
            """,
        ),
        down=("DROP TABLE eval_result", "DROP TABLE eval_plan"),
    ),
    Migration(
        version=19,
        summary="idempotent local setup-store imports",
        up=(
            """
            CREATE TABLE store_port_import (
                import_key      TEXT PRIMARY KEY,
                adapter         TEXT NOT NULL,
                snapshot_digest TEXT NOT NULL,
                external_id     TEXT NOT NULL,
                stable_id       TEXT NOT NULL REFERENCES entity(stable_id),
                revision_id     TEXT NOT NULL REFERENCES revision(revision_id),
                imported_at     TEXT NOT NULL,
                UNIQUE (adapter, snapshot_digest, external_id)
            ) STRICT
            """,
        ),
        down=("DROP TABLE store_port_import",),
    ),
    Migration(
        version=20,
        summary="append-only GitHub repository lifecycle observations",
        up=(
            """
            CREATE TABLE github_repository_observation (
                observation_id      INTEGER PRIMARY KEY,
                stable_id           TEXT NOT NULL REFERENCES entity(stable_id),
                version             TEXT NOT NULL,
                passport_digest     TEXT NOT NULL,
                source_repository   TEXT NOT NULL,
                repository_id       INTEGER NOT NULL,
                repository_full_name TEXT NOT NULL,
                archived            INTEGER NOT NULL CHECK (archived IN (0, 1)),
                etag                TEXT,
                fetched_at          TEXT NOT NULL,
                expires_at          TEXT NOT NULL,
                response_kind       TEXT NOT NULL
                    CHECK (response_kind IN ('modified', 'not_modified'))
            ) STRICT
            """,
            "CREATE INDEX github_observation_by_version ON github_repository_observation"
            "(stable_id, version, observation_id)",
        ),
        down=(
            "DROP INDEX github_observation_by_version",
            "DROP TABLE github_repository_observation",
        ),
    ),
    Migration(
        version=21,
        summary="a setup's publication and the components it pins are one decision",
        up=(
            """
            CREATE TABLE setup_publication_set (
                set_digest       TEXT PRIMARY KEY,
                setup_stable_id  TEXT NOT NULL,
                setup_version    TEXT NOT NULL,
                account_id       TEXT NOT NULL,
                device_id        TEXT NOT NULL,
                members_json     TEXT NOT NULL,
                state            TEXT NOT NULL,
                created_at       TEXT NOT NULL
            ) STRICT
            """,
            # One open set per exact setup version. A second plan for the same
            # version is the same decision made twice, and confirming the older
            # one after the newer would publish a graph nobody reviewed.
            "CREATE UNIQUE INDEX setup_publication_set_open_uq ON setup_publication_set"
            "(account_id, setup_stable_id, setup_version) WHERE state != 'published'",
        ),
        down=(
            "DROP INDEX setup_publication_set_open_uq",
            "DROP TABLE setup_publication_set",
        ),
    ),
    Migration(
        version=22,
        summary="installation plans bind provider release trust evidence",
        up=(
            "ALTER TABLE operation_plan ADD COLUMN provider_release_trust TEXT",
            "ALTER TABLE operation_plan ADD COLUMN provider_release_evidence TEXT",
        ),
        down=(
            "ALTER TABLE operation_plan DROP COLUMN provider_release_evidence",
            "ALTER TABLE operation_plan DROP COLUMN provider_release_trust",
        ),
    ),
    Migration(
        version=23,
        summary="a verified program operation records which build it exposed",
        # The same argument that added `setup_version`: the version is in the
        # effect prose, and reading a version out of a sentence written for a
        # person is parsing prose. `harness status` has to name the exact build
        # standing under a prefix, and asking the program itself would run a
        # foreign binary from a command declared `read`.
        #
        # Written at verify time beside `verified_target_digest`, because only
        # the provider's apply answer knows them.
        up=(
            "ALTER TABLE operation_plan ADD COLUMN program_version TEXT",
            "ALTER TABLE operation_plan ADD COLUMN program_entry_point TEXT",
        ),
        down=(
            "ALTER TABLE operation_plan DROP COLUMN program_entry_point",
            "ALTER TABLE operation_plan DROP COLUMN program_version",
        ),
    ),
    Migration(
        version=24,
        summary="record the catalogue's trust verdict for an acquired version",
        up=(
            """
            CREATE TABLE acquired_trust (
                stable_id          TEXT NOT NULL REFERENCES entity(stable_id),
                version            TEXT NOT NULL,
                passport_digest    TEXT NOT NULL,
                trust_lane         TEXT NOT NULL,
                author_verified    INTEGER NOT NULL,
                component_verified INTEGER NOT NULL,
                acquired_at        TEXT NOT NULL,
                PRIMARY KEY (stable_id, version)
            ) STRICT
            """,
        ),
        down=("DROP TABLE acquired_trust",),
    ),
    Migration(
        version=25,
        summary="record what a consent fingerprint was taken from",
        up=(
            # A fingerprint of `{}` cannot be told apart from a fingerprint of
            # objects that genuinely need nothing, and the two must not decide
            # the same way: the first has observed no shape and has to ask
            # again, the second is a real ceiling. So the record now carries the
            # identities it was taken from.
            #
            # Existing rows get `[]` and therefore stop covering. That is the
            # safe direction and costs nothing real: every row written before
            # this migration held `fingerprint_of({})`, which already refused
            # every candidate needing anything at all.
            "ALTER TABLE consent ADD COLUMN observed TEXT NOT NULL DEFAULT '[]'",
        ),
        down=("ALTER TABLE consent DROP COLUMN observed",),
    ),
    Migration(
        version=26,
        summary="remember which provider executable serves each harness",
        up=(
            # One row per harness, because "which provider runs" must have one
            # answer. `#452`: the choice used to live in whichever `--provider`
            # argument the last command carried, which is not a place a later
            # command can read.
            """
            CREATE TABLE provider_installation (
                harness_id        TEXT PRIMARY KEY,
                path              TEXT NOT NULL,
                source            TEXT NOT NULL,
                state             TEXT NOT NULL,
                provider_id       TEXT NOT NULL,
                provider_version  TEXT NOT NULL,
                tag               TEXT NOT NULL,
                commit_sha        TEXT NOT NULL,
                artifact_digest   TEXT NOT NULL,
                checked_at        TEXT NOT NULL,
                source_checked_at TEXT NOT NULL
            ) STRICT
            """,
        ),
        down=("DROP TABLE provider_installation",),
    ),
    Migration(
        version=27,
        summary="a program plan binds the harness, the provider bytes and the prefix it read",
        # What a stopped program operation used to be: an action, a prefix in
        # `target_id`, and a target in `provider_target`. Everything else that
        # said *which* operation this was — the harness, the executable, the
        # release that was trusted, what stood under the prefix when it was
        # planned — arrived again from whoever ran `harness resume`, so a
        # different provider pointed at a different prefix settled it.
        #
        # These four make the operation its own subject. `program_prefix_state`
        # is the reading `provider/program_state.py` took at plan time: not a
        # digest, because settling needs to know *what changed*, and a digest
        # only says that something did.
        up=(
            "ALTER TABLE operation_plan ADD COLUMN program_harness_id TEXT",
            "ALTER TABLE operation_plan ADD COLUMN program_entry_point_planned TEXT",
            "ALTER TABLE operation_plan ADD COLUMN program_prefix_state TEXT",
            "ALTER TABLE operation_plan ADD COLUMN provider_artifact_digest TEXT",
        ),
        down=(
            "ALTER TABLE operation_plan DROP COLUMN provider_artifact_digest",
            "ALTER TABLE operation_plan DROP COLUMN program_prefix_state",
            "ALTER TABLE operation_plan DROP COLUMN program_entry_point_planned",
            "ALTER TABLE operation_plan DROP COLUMN program_harness_id",
        ),
    ),
    Migration(
        version=28,
        summary="a device remembers the sync events it was told to abandon",
        # `--skip-event` names an exact event a device walks past, abandoning
        # its revision. Naming it once used to mean naming it on every later
        # pull as well: the ids were flags and nothing kept them, so a device
        # recovering from an abandoned lineage had to carry a growing list
        # across invocations. An abandonment is a decision this device made
        # about this account's stream; it is recorded here and honoured by
        # every later pull without being repeated.
        up=(
            """
            CREATE TABLE sync_abandoned_event (
                account_id   TEXT NOT NULL,
                event_id     TEXT NOT NULL,
                abandoned_at TEXT NOT NULL,
                PRIMARY KEY (account_id, event_id)
            ) STRICT
            """,
        ),
        down=("DROP TABLE sync_abandoned_event",),
    ),
    Migration(
        version=29,
        summary="recoverable consumer-owned multi-root installation transactions",
        up=(
            """
            CREATE TABLE installation_transaction (
                transaction_id      TEXT PRIMARY KEY,
                idempotency_key     TEXT NOT NULL UNIQUE,
                transaction_digest TEXT NOT NULL UNIQUE,
                setup_stable_id     TEXT NOT NULL,
                setup_version       TEXT NOT NULL,
                harness_id          TEXT NOT NULL,
                state               TEXT NOT NULL CHECK (
                    state IN (
                        'planned', 'applying', 'compensating',
                        'recovery_required', 'verified', 'rolled_back'
                    )
                ),
                approved_digest     TEXT,
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL
            ) STRICT
            """,
            """
            CREATE TABLE installation_transaction_child (
                transaction_id TEXT NOT NULL
                    REFERENCES installation_transaction(transaction_id),
                position       INTEGER NOT NULL,
                scope          TEXT NOT NULL CHECK (
                    scope IN ('global', 'user_root', 'project')
                ),
                operation_id   TEXT NOT NULL UNIQUE
                    REFERENCES operation_plan(operation_id),
                target_id      TEXT NOT NULL,
                plan_digest    TEXT NOT NULL,
                state          TEXT NOT NULL,
                backup_ref     TEXT,
                PRIMARY KEY (transaction_id, position),
                UNIQUE (transaction_id, scope),
                UNIQUE (transaction_id, target_id)
            ) STRICT
            """,
            """
            CREATE TABLE installation_transaction_target (
                target_id      TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL
                    REFERENCES installation_transaction(transaction_id)
            ) STRICT
            """,
            """
            CREATE TABLE installation_transaction_event (
                transaction_id TEXT NOT NULL
                    REFERENCES installation_transaction(transaction_id),
                sequence       INTEGER NOT NULL,
                at             TEXT NOT NULL,
                state_before   TEXT NOT NULL,
                state_after    TEXT NOT NULL,
                result         TEXT NOT NULL,
                PRIMARY KEY (transaction_id, sequence)
            ) STRICT
            """,
        ),
        down=(
            "DROP TABLE installation_transaction_event",
            "DROP TABLE installation_transaction_target",
            "DROP TABLE installation_transaction_child",
            "DROP TABLE installation_transaction",
        ),
    ),
)

#: Names for nested savepoints. A counter rather than a fixed name: two nested
#: transactions with one name would release the outer when the inner finished.
_SAVEPOINTS: Final[Iterator[int]] = count()


#: How long a statement waits for another process to finish writing. Bootstrap
#: writes take milliseconds; this is generous enough that a wait means trouble.
# The third measured Windows runner contention held a first-open migration lock
# for 6439 ms in run 33790300140. Fifteen seconds is more than twice that
# observed maximum while remaining a bounded refusal.
BUSY_TIMEOUT_MILLISECONDS: Final[int] = 15_000

#: How long to keep trying to switch the journal mode while another opener
#: holds the lock. Short: the switch itself takes microseconds.
MODE_SWITCH_SECONDS: Final[float] = 5.0

#: The newest schema this build understands.
SCHEMA_VERSION: Final[int] = MIGRATIONS[-1].version


def configured_path() -> Path:
    """Where the registry lives, from the effective configuration.

    Here rather than in a command module: it is a fact about the registry, and
    two commands needing it must not mean one importing the other.
    """
    from ai_stp_cli import config

    report = config.effective_config()
    location = next(value for value in report.values if value.path == "registry.path")
    return Path(str(location.value))


def _apply_permissions(path: Path) -> None:
    """Owner-only on the database and on the files WAL creates beside it.

    SQLite creates the journal and shared-memory files itself, so their mode
    comes from the process umask rather than from the mode the database was
    given. They hold the same rows.
    """
    if not POSIX:  # pragma: no cover - the coverage leg is Linux; Windows asserts this
        return
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            candidate.chmod(FILE_MODE)


def open_registry(path: Path, *, create: bool = True) -> sqlite3.Connection:
    """Open the registry, applying any pending migrations.

    Deterministic on a clean home and on reopening: the same file comes back at
    the same schema version, and applying migrations again is a no-op.
    """
    if not create and not path.exists():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the local registry does not exist yet",
            details={"path": redact_home(path)},
            next_actions=["passport developer init --json"],
        )
    ensure_directory(path.parent)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        # First, because it governs every statement after it — including the
        # switch to WAL, which briefly needs an exclusive lock and fails outright
        # against a database another process is opening at the same moment.
        # SQLite defaults to giving up on a busy database immediately, and an
        # agent runs several `ai-stp` calls at once.
        connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MILLISECONDS}")
        enable_write_ahead_logging(connection)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        _migrate(connection, path)
    except BaseException:
        connection.close()
        raise
    _apply_permissions(path)
    return connection


def enable_write_ahead_logging(connection: sqlite3.Connection) -> None:
    """Put the database in write-ahead logging, tolerating a lost race.

    Changing the journal mode takes a brief exclusive lock, and SQLite does not
    reliably apply the busy handler to that statement — so two processes opening
    a fresh registry at the same moment can have one of them refused outright.

    Retried rather than checked once. The first version asked again immediately
    after a refusal and re-raised if the mode was not yet `wal`, which lost to
    the very race it was written for: the winner had taken the lock but not yet
    committed the change, so the loser saw the old mode and gave up. What matters
    is the mode shortly afterwards, not who set it or exactly when.
    """
    deadline = time.monotonic() + MODE_SWITCH_SECONDS
    while True:
        if str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal":
            return
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def open_readonly(path: Path) -> sqlite3.Connection:
    """Open the registry without touching it.

    `open_registry` applies pending migrations, which is a write. A diagnostic
    is declared `read` and must be able to look at a database it is not allowed
    to change — including one written by a newer build, which it must be able to
    describe rather than refuse to open.
    """
    if not path.exists():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the local registry does not exist yet",
            details={"path": redact_home(path)},
            next_actions=["passport developer init --json"],
        )
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MILLISECONDS}")
    try:
        # The first read is what initializes WAL access, and in WAL mode it
        # needs the `-shm` index created beside the file — a directory write.
        # Probed here so the fallback below is taken while the failure is
        # still this function's to explain.
        connection.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
    except sqlite3.OperationalError as error:
        text = str(error).lower()
        if "readonly database" not in text and "unable to open database file" not in text:
            raise
        connection.close()
        if (path.parent / (path.name + "-wal")).exists():
            # A live WAL session exists that this reader cannot join without
            # the shared index; pretending the file is frozen would read a
            # state no writer ever committed.
            raise
        # No `-wal` and no way to create one in this directory: nothing can
        # start a write session here, so the file is immutable in fact, and
        # saying so is what lets sqlite read it without touching the
        # directory. Measured across the read surface before this branch:
        # five read commands answered `AI_STP_INTERNAL` against a data
        # directory without write permission.
        connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        connection.row_factory = sqlite3.Row
    return connection


def file_schema_version(path: Path) -> int:
    """The schema version of a registry file, without opening it read-write.

    Opening through `open_registry` applies pending migrations, which is a
    write. A diagnostic must be able to look without changing anything, so this
    reads the header field through a read-only connection.
    """
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return schema_version(connection)
    finally:
        connection.close()


def schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def _migrate(connection: sqlite3.Connection, path: Path) -> None:
    current = schema_version(connection)
    if current > SCHEMA_VERSION:
        # Refused, not downgraded: a newer build may have written rows this one
        # cannot represent, and opening read-write would be the one way to lose
        # them. The file is left exactly as it was found.
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the local registry was written by a newer build",
            details={
                "path": redact_home(path),
                "found": str(current),
                "supported": str(SCHEMA_VERSION),
            },
            next_actions=["version --json"],
        )
    for migration in MIGRATIONS:
        if migration.version <= current:
            continue
        _run(connection, migration.up, migration.version, skip_if_reached=migration.version)


def _run(
    connection: sqlite3.Connection,
    statements: Sequence[str],
    version: int,
    *,
    skip_if_reached: int | None = None,
) -> None:
    """Apply one migration and its version stamp in a single transaction."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        # The version was read before this transaction began, and another
        # process may have applied the same migration in between. Asking again
        # under the write lock is what makes concurrent first runs safe: the
        # loser here finds the work already done instead of re-creating tables.
        #
        # Only meaningful going forward. A downgrade stamps a *lower* version by
        # design, so the same test would skip every reverse step — which it did.
        if skip_if_reached is not None and schema_version(connection) >= skip_if_reached:
            connection.execute("ROLLBACK")
            return
        for statement in statements:
            connection.execute(statement)
        # `PRAGMA user_version` takes no parameter binding.
        connection.execute(f"PRAGMA user_version={int(version)}")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def downgrade(connection: sqlite3.Connection, target: int) -> None:
    """Step the schema back, refusing where no reverse was declared."""
    for migration in reversed(MIGRATIONS):
        if migration.version <= target or migration.version > schema_version(connection):
            continue
        if not migration.down:
            raise CliFailure(
                "AI_STP_UNSUPPORTED_APPLY",
                "this migration declares no reverse and will not be guessed",
                details={"version": str(migration.version), "summary": migration.summary},
            )
        _run(connection, migration.down, migration.version - 1)


@contextmanager
def transaction(connection: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    """One durable unit of work: everything or nothing.

    `BEGIN IMMEDIATE` takes the write lock up front, so two processes cannot
    both read, both decide, and then both write.

    Nested use becomes a savepoint, because SQLite refuses a second `BEGIN` and
    would fail the outer work with an error about transactions rather than about
    anything the caller did. A large atomic operation is often built from small
    ones that are atomic on their own — freezing a version records a revision —
    and without this the outer one would have to reimplement the inner or give
    up the guarantee it exists to provide.
    """
    if connection.in_transaction:
        # The name is generated here from a counter, never from input, so it is
        # safe to interpolate: SQLite has no parameter binding for savepoints.
        name = f"nested_{next(_SAVEPOINTS)}"
        connection.execute(f"SAVEPOINT {name}")
        try:
            yield connection
        except BaseException:
            # Rolling back to a savepoint leaves it on the stack, so the release
            # is not part of the recovery — it is what removes it either way.
            connection.execute(f"ROLLBACK TO {name}")
            connection.execute(f"RELEASE {name}")
            raise
        connection.execute(f"RELEASE {name}")
        return

    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")
