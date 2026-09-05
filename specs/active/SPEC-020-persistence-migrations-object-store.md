---
description: "SPEC-020: Server-side storage, PostgreSQL migrations and immutable object storage."
last_verified: "2026-09-04"
---

# SPEC-020: Server storage, migrations and immutable object storage

## Purpose

The server platform gets a durable foundation: a single `Alembic` migration tree
for PostgreSQL, the initial Sprint-1 schema with its constraints, a separate
object location table and `RustFS`/`S3` adapter for immutable bytes with
integrity checks. The platform mechanism is defined in `ADR-0009`; content ID and
canonicalization belong to `SPEC-015` and `ADR-0036`; the queue model and its migration
belong to `SPEC-018`, but live in the same migration tree.

## Scope

Includes: `SQLAlchemy 2` and `Alembic` configuration for server-side PostgreSQL;
policies for applying, repeating, rolling back, and forward-fixing migrations; initial
Sprint-1 tables and constraints for accounts, `OAuth` identities, devices,
sessions, public catalog metadata, object locations, and audit events;
object location table as a link between metadata and the storage key; adapter
`RustFS`/`S3` immutable record with digest and size check; definition
migration readiness as reaching `head`; deterministic test fixtures
and complete state cleanup.

Not included: domain semantics of columns of accounts, identities, devices, sessions
and the catalog that belongs to `SPEC-002`, `SPEC-003`, `SPEC-004`, `SPEC-005` and
general wire diagrams `#71`; queue model and migration (`SPEC-018`); event tables
synchronizations that are authored by `SPEC-025` and live in the same migration tree;
tables of rights, invitations, complaints, scans of checks and publication plans,
which are authored by `SPEC-026` / `#181` and live in the same migration tree;
real publication and check handlers (logic - `SPEC-026`); network
concealment and `docker-compose`
(`SPEC-019`); ready as REST surface (`SPEC-017`); data management and
retention policy (`SPEC-013`); production infrastructure and public access.

## Terms

- `Migration tree` - a single linear history of the `Alembic` PostgreSQL server schema,
  common to all platform tables, including the queue table from `SPEC-018`.
- `Forward-fix` - eliminating the defect of the applied migration with a new forward migration, and
  not a rollback of an already advanced schema.
- `Object location` - a string linking the metadata of the catalog or passport with
  an opaque content-addressable key of an object in the store.
- `Immutable object write` - recording bytes under the key, which checks digest and
  size and rejects other bytes under the same key.

## Requirements

- `REQ-2001`: The PostgreSQL server schema is managed by a single `Alembic` migration
  tree; `upgrade head` applies to an empty database, re-running it creates no
  divergence, and the history is linear without parallel heads outside the merge window.
- `REQ-2002`: Each migration defines a forward operation and a reverse operation, or
  explicitly marks itself irreversible; the default recovery policy is forward-fix,
  and `downgrade` is allowed only within the compatibility window before code promotion,
  under `docs/operations/runbooks/database-migration.md`.
- `REQ-2003`: The initial Sprint-1 schema creates account tables,
  `OAuth` identities, devices, sessions, public catalog metadata,
  object locations, and audit events with primary keys, foreign keys, and
  unique constraints; column semantics belong to the domain owners, while this
  specification owns only the storage layer and integrity constraints.
  **Multi-version catalog:** `catalog_metadata` allows **multiple rows**
  for one `(object_kind, stable_id)` (different `version` / X.Y); uniqueness is not
  reduced to one row per object (an evolution of the earlier constraint, issue
  `#143`, `SPEC-005`). Publication state (`published_at`, trust line, verification
  axes) is stored in columns of the same table under `ADR-0042` / `SPEC-021`.
- `REQ-2004`: Object location table associates metadata record with key
  object in storage; the object key is opaque, content-addressed, and does not by
  itself grant access to bytes. Multiple catalog rows (different
  `version` of the same object or different objects) can point to the same
  key when the artifact digest matches. A row is unique by the pair
  `(catalog_metadata_id, purpose)`. The immutability of the bytes under the key belongs to
  storage adapter (`REQ-2005`) rather than a unique constraint on the pointer.
- `REQ-2005`: The `RustFS`/`S3` adapter writes immutable bytes only after
  digest and size checks; writing other bytes under an existing key
  is rejected by a typed conflict error, and re-writing identical bytes
  under the same key is idempotent and does not create a second effect.
- `REQ-2006`: Digest and content ID of the object are calculated according to the canonical rules
  `SPEC-015` and `ADR-0036`; The storage layer does not introduce its own canonicalization or other
  hash area.
- `REQ-2007`: Migration readiness is determined by achieving `Alembic head`; layer
  storage provides this check for consumption by the `SPEC-017` readiness, not
  duplicating the REST readiness surface.
- `REQ-2008`: The audit event table only allows adding at level
  limitations of the normal recording path; changing and deleting an audit line is not included
  the usual path, and the data management semantics belong to `SPEC-013`.
- `REQ-2009`: Deterministic test fixtures create and completely remove
  condition; teardown does not leave shared data between tests via schema isolation
  or transactions.
- `REQ-2010`: Public catalog search uses table `catalog_search_projection` with
  one row per `(object_kind, stable_id)`, PostgreSQL arrays for tags and
  harnesses, a stored weighted `tsvector` with GIN, and composite B-tree
  indexes for `updated_at` and `likes` sorts. The migration is reversible.
  `pg_trgm` is not enabled unless a query uses it.

## States and errors

Migration application completes successfully, with a typed error for an incompatible
or divergent history, or with a database-unavailable error. An immutable object write
completes successfully when the digest and size match, idempotently when identical
bytes already exist under the same key, and with a typed conflict error when different
bytes exist under the key or when the digest or size does not match. A foreign-key,
unique-constraint, or audit-constraint violation is a typed storage error and does not
produce a partial write.

## Security and privacy

The object key is opaque and is not a permission: access to the bytes is granted
a separate verified server step, and not knowledge of the key. Secrets, tokens,
environmental values and optional personal data are not included in the schema,
migrations, fixtures and audit records. PostgreSQL and `RustFS` are available only to servers
components and are not published on the Internet according to `SPEC-019`. Audit records are based on
allowed list of fields `SPEC-013` and do not contain secrets.

## Compatibility and migration

The schema evolves through a sequence of expansion, backfill, switchover, and removal
according to `SPEC-010` and `docs/engineering/schema-evolution.md`. New field first
added optional. A backwards-incompatible change goes through the double window
reading before deleting the old path. Recovering from a defective migration
forward-fix is executed by default; `downgrade` only applies while advanced
the code is compatible with the data recorded by the new version. Changing the digest area or
canonicalization of an object requires a new version under `SPEC-015`.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-2001` | The test applies `upgrade head` on an empty base, repeats the application without discrepancy and confirms the only head of the story. |
| `REQ-2002` | The migration test confirms the presence of a reverse operation or irreversibility mark and follows the forward-fix on the runbook. |
| `REQ-2003` | The migration creates Sprint-1 tables with primary, foreign and unique keys, which are confirmed by negative constraint violation tests. |
| `REQ-2004` | The object location test associates metadata with an opaque key and confirms that the key itself does not provide access to bytes; two versions with one artifact digest each receive the line `object_location` with one `object_key`. |
| `REQ-2005` | The adapter test confirms digest and size checks, idempotency of identical bytes and a conflict error for other bytes under the same key. |
| `REQ-2006` | The digest test uses the `SPEC-015` reference vectors and does not introduce a second canonicalization. |
| `REQ-2007` | The readiness test confirms that migration readiness is only true when `head` is reached. |
| `REQ-2008` | The audit test confirms the rejection of a row change and deletion in the normal write path. |
| `REQ-2009` | Running the test suite confirms that teardown does not leave shared state between tests. |
| `REQ-2010` | Migration tests create `catalog_search_projection` with unique `(object_kind, stable_id)`, GIN on `search_vector`, array GIN, and partial B-tree sort indexes, and the downgrade drops the table. |
