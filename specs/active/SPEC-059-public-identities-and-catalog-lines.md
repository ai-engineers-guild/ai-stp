---
description: "SPEC-059: Unique account identities, component names, and owner-fenced catalog lines."
last_verified: "2026-09-04"
---

# SPEC-059: Public identities and catalog lines

## Purpose

Make every public account and component line unambiguous, prevent impersonation
through equivalent names, and prevent a publisher from adding a version to a
line owned by another account.

## Scope

Included: account ID, handle and public display-name uniqueness; Official
identity reservation; component stable ID, canonical name, RU/EN display names
and line ownership; normalization; publication fencing; migration conflicts.
Excluded: OAuth provider aliases, search synonyms, ownership-request review,
and upstream synchronization, which belong to their existing specifications.

## Terms

- **Public handle** — the unique ASCII account name used in routes and machine
  references.
- **Catalog line** — the mutable identity and current owner shared by every
  immutable version of one `stable_id`.
- **Canonical name** — the globally unique language-independent component name.
- **Localized display name** — the unique RU or EN presentation name of a line.

## Requirements

- `REQ-5901`: Every account has one opaque primary ID, one public handle, and
  one public display name. The database rejects a duplicate normalized handle
  or display name under concurrent creation or rename.
- `REQ-5902`: Shared versioned normalization applies Unicode NFKC, trimming,
  whitespace collapse, and casefold. A handle additionally accepts only the
  closed ASCII handle grammar. API, CLI, migration checks, and database keys use
  the same normalization version.
- `REQ-5903`: The fixed AI STP Official account ID, `ai-stp-official` handle,
  and `AI STP Official` display name are seeded idempotently and cannot be
  assigned, renamed, or transferred by an ordinary account operation.
- `REQ-5904`: Every component `stable_id` has exactly one catalog-line row with
  one current owner and one globally unique normalized canonical name. Every
  catalog version references that row; a version cannot carry a different
  effective owner.
- `REQ-5905`: A component line has exactly one RU and one EN display name. The
  normalized display name is unique within its locale; public and machine reads
  return locale, submitted display spelling, canonical name, and stable ID.
- `REQ-5906`: Publication verifies the current line owner when a plan is created
  and repeats the check under the publishing transaction. A plan made stale by
  ownership transfer fails without creating catalog metadata or object bytes.
- `REQ-5907`: Ownership changes only through an append-only ownership revision
  that atomically updates the catalog line. Immutable passport owner fields and
  historical publisher attribution are never rewritten.
- `REQ-5908`: Migration inventories normalized conflicts before enabling unique
  constraints. A conflict blocks constraint activation and is reported with
  opaque IDs; migration never silently renames, merges, or selects an owner.

## States and errors

Identity allocation is either accepted or rejected without partial profile or
catalog state. Stable errors distinguish handle conflict, account display-name
conflict, canonical component-name conflict, localized component-name conflict,
foreign line ownership, stale ownership revision, and migration conflict.

## Security and privacy

Normalization prevents visually equivalent Official-name registration but is
not a general visual-similarity classifier. Public identity responses contain no
OAuth subject, email, or private provider metadata. Ownership checks execute on
the server and cannot be bypassed by passport fields.

## Compatibility and migration

Add identity columns and catalog-line tables before backfill. Existing reads
continue while conflicts are inventoried. After operator resolution, add unique
indexes, populate version foreign keys, enable owner fencing, and only then stop
reading version-level ownership as current ownership.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-5901` | PostgreSQL concurrency tests reject exact and normalized handle and display-name collisions. |
| `REQ-5902` | One normalization corpus produces identical versioned keys in foundation, API, CLI, migration checks, and database fixtures. |
| `REQ-5903` | The fixed Official identity cannot be claimed or renamed through public operations. |
| `REQ-5904` | Migration and publication tests establish one owner and canonical name per stable ID. |
| `REQ-5905` | Contract and PostgreSQL tests reject duplicate RU/EN names in the same locale and expose exact localized identity fields. |
| `REQ-5906` | A foreign account and a pre-transfer stale plan both fail to publish a new version without side effects. |
| `REQ-5907` | A transfer changes current owner once while exact historical version reads retain original provenance. |
| `REQ-5908` | A collision fixture blocks constraint activation and emits a deterministic conflict report without rewriting names. |

## Required checks

Run `just docs-gen`, `just docs-check`, `just back-static`, and `just back-test`.
