---
description: "SPEC-025: Private registry and server-side revision synchronization."
last_verified: "2026-08-15"
---

# SPEC-025: Private registry and server-side revision synchronization

## Purpose

The server layer provides an authorized device with a minimal private registry:
it accepts content-addressed revisions, stores the entity head, and returns an
ordered stream of accepted events. This implements the server side of
`SPEC-009` without moving local registry, merge, or installation logic into the
API.

## Scope

Included are authenticated sending and receiving of bounded event batches,
durable revisions and heads, idempotent receipts, an account-scoped cursor,
fast-forward, an explicit conflict response, tombstones, and device revocation.
Tables and migrations belong to this slice but live in the shared Alembic tree
under `SPEC-020`; event fields and their formats belong to
`docs/contracts/sync-event.md`, and the wire models later become the OpenAPI
source under `SPEC-010`.

Excluded are CLI synchronization implementation (`#180`), automatic or
server-side merging, CRDTs, a message broker, serving artifact bytes,
publication, grants, a web synchronization-status screen, and physical data
deletion.

## Terms

- `Revision ledger` — immutable accepted revisions and their parents within one
  account.
- `Head` — the single current entity revision accepted by the server.
- `Receipt` — the durable result of processing one event; a retry returns it
  rather than creating a second effect.
- `Server outbox` — an ordered stream of accepted events from which devices read
  changes; it does not need a separate broker.

## Requirements

- `REQ-2501`: In its initial form, the server ledger accepts and serves only the
  cross-device developer passport, the permitted summary of a specific device,
  private component or setup revisions, scoped consent, and their tombstones for
  the current account. This slice does not store artifact bytes, backups, a full
  passport or project index, absolute paths, secrets, or environment values.
- `REQ-2502`: Every event has an account-scoped idempotent receipt. Retrying the
  same event, or retrying after a lost response, returns the original result,
  head, and cursor without a second revision, outbox record, or audit record.
- `REQ-2503`: Revision acceptance, the head transition, append to the server
  outbox, and the receipt are committed in one PostgreSQL transaction. Before
  commit, a receiver cannot see the event; rollback leaves no partial result.
- `REQ-2504`: Retrieval starts from an opaque account-bound cursor over the
  ordered server outbox, limits the batch size, and stores no per-client cursor
  state on the server. The cursor is not an offset, entity ID, or authority over
  another account. A non-empty page returns the cursor of the last sequence
  served regardless of whether more rows exist when the response is produced.
  An empty page does not advance the position or force a client that has already
  consumed events to restart the stream from zero.
- `REQ-2505`: The server accepts only an initial revision or a fast-forward from
  the expected current head. For diverging history, it returns an explicit
  `conflict` with enough revisions to find a common ancestor, applies no
  last-write-wins rule, and does not change the head.
- `REQ-2506`: A tombstone is an ordinary accepted revision and is visible in the
  server outbox. It closes ordinary reads under `SPEC-013` but does not delete
  history required for recovery or a three-way merge.
- `REQ-2507`: The client constructs a merge from the common ancestor under
  `SPEC-009`. The server accepts only an explicitly created resulting revision
  with the required parents; it does not merge fields, choose a winner, or
  change the installed harness target.
- `REQ-2508`: A request is permitted only for an active device bound to the
  current server session; an event cannot declare another device. A revoked
  device receives a permanent rejection before any revision, head, outbox, or
  receipt is written.
- `REQ-2509`: Private events are isolated by account, while successful
  acceptance, conflict, and rejection due to revocation produce safe structural
  signals and append-only audit records without the revision document, tokens,
  signatures, or secrets.
- `REQ-2510`: The slice uses PostgreSQL and the existing minimal worker only
  where a real asynchronous effect arises. The server outbox itself is read
  synchronously from the durable ledger and creates neither a fictitious job nor
  a new external dependency.

## Security and privacy

Authorization always determines the account and active device on the server;
event fields cannot expand that authority. A cursor only continues reading an
already authorized account stream and is integrity-checked. The revision
document is stored and served exclusively for the entity allowlist, while
audit, logs, and metrics carry only safe identifiers, the result, and
correlation data under `SPEC-013` and `SPEC-017`.

## States and errors

A receipt has the `accepted`, `rejected`, `conflict`, and `superseded` states
from `SPEC-009`. The client session remains `offline`, `pushing`, `pulling`,
`conflict`, `partial`, `failed`, or `up_to_date`; the server does not declare it
successful on the client's behalf. An invalid schema, invalid revision,
foreign entity, and precondition violation receive stable typed errors; a
revoked device returns `AI_STP_DEVICE_REVOKED`.

## Compatibility and migration

New tables are added through an additive Alembic migration with foreign keys,
receipt uniqueness, and an index on the ordered outbox. Event forms first pass
through `packages/contracts`, fixtures, and generated OpenAPI; an older
supported client receives only compatible fields. Compaction, revision
deletion, and cursor expiry are outside #179 and cannot delete an ancestor
available to a supported device.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-2501` | Contract/API tests reject artifact bytes and secret or prohibited fields; another account cannot read the events. |
| `REQ-2502` | Retrying one event after simulating a lost response returns an identical receipt, one revision, and one cursor. |
| `REQ-2503` | Fault injection before commit leaves neither a head nor an event; a successful commit makes all four parts visible together. |
| `REQ-2504` | Two pull batches traverse the stream without gaps or duplicates; a non-empty page, including the last one, returns a cursor; another pull with that cursor returns an empty page; one new event after the saved cursor arrives by itself; a forged or foreign cursor is rejected. |
| `REQ-2505` | Two devices fast-forward sequentially, while diverging changes return conflict and preserve the old head. |
| `REQ-2506` | A tombstone reaches the second device as a revision, closes ordinary reads, and preserves the graph for recovery. |
| `REQ-2507` | An explicit merge revision with two parents is accepted, but the server never creates it itself. |
| `REQ-2508` | Device revocation prohibits push and pull without a side effect, while local reads are not checked by the server. |
| `REQ-2509` | Audit/log tests record safe identifiers and contain no document, token, signature, or secret. |
| `REQ-2510` | An integration test proves that sync works without a broker and without a job when there is no asynchronous projection. |
