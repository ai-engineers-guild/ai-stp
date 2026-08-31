---
description: "Decision on minimal server-side synchronization through a revision ledger and account-scoped outbox."
last_verified: "2026-08-07"
---

# ADR-0045: Minimal Server-Side Synchronization Through a Revision Ledger

Status: accepted.

## Context

`ADR-0005` and `SPEC-009` already require a revision graph, fast-forward,
three-way merge, conflicts, and tombstones. After Sprint 1, PostgreSQL, Alembic,
active devices with opaque server-side sessions, and a minimal PostgreSQL queue
exist. For #179, the private server-side path must be materialized without bringing
in a broker, CRDT, or a second implementation of the local registry.

## Options

1. A broker or CDC stream as the synchronization transport. Provides a separate
   transport, but adds a service, operations, redelivery, and a second source of
   ordering before there is load to justify them.
2. Last-write-wins or automatic server-side merging. Appears shorter, but loses
   confirmed changes and directly contradicts `ADR-0005`.
3. A PostgreSQL revision ledger, one server-side head per entity, durable receipts,
   and an ordered append-only outbox read by clients through a cursor.

## Decision

Option 3 is accepted.

The server stores four minimal roles in one PostgreSQL schema; every record is
isolated by account, and the head is unique by the account and entity pair:

- an immutable revision with a canonical payload and parents;
- the entity's current head in the account;
- a receipt for the idempotent event;
- an append-only server outbox with a monotonic sequence.

Event acceptance serializes the entity head and validates the account, active
device, schema, content-addressed revision, parents, and expected head. In one
transaction, it writes the revision if necessary, advances the head, adds an outbox
entry, and stores the receipt. A retry returns the stored receipt. For a batch,
events are processed in client order; a partial batch truthfully returns per-item
results and does not roll back already committed preceding events.

Pull reads the server outbox through a signed account-scoped cursor. The cursor
carries only the position and is validated with a separate signing scope of the
existing server secret; neither a separate environment variable nor a server-side
cursor table is needed. It does not replace authorization and does not expose the
ordering or events of another account.

Fast-forward is allowed when the expected current head is a parent of the new
revision. Divergence returns `conflict` with the heads and common ancestor; the
server does not perform LWW, CRDT, or field merging. A valid conflicting candidate
remains in the ledger without advancing the head and without an outbox event, so the
client can refer to it later in an explicit revision with two parents. A tombstone
follows the same path and does not delete history required by the graph.

For #179, the server outbox is itself the durable stream of accepted sync events.
The worker and its `job` table do not receive an empty sync job: they are connected
later only for a real asynchronous projection, such as publication or notification
delivery. Exact models, routes, and codes come from `packages/contracts` and the
generated OpenAPI; this decision does not create a parallel wire contract.

## Consequences

- additive Alembic models and a migration are added for the revision ledger, head,
  receipt, and outbox; no new dependency or broker is needed;
- a separate synchronization API slice is introduced, using the existing session
  authentication and active-device validation;
- the cursor must be signed, bounded, and bound to the account; revoking or reissuing
  it does not affect data and merely requires a new pull from a safe position;
- contract, API, and PostgreSQL integration checks will be required for retries,
  concurrent pushes, the cursor, tombstones, conflicts, merge revisions, and
  revocation;
- the CLI client, web synchronization state, grants, publication, cleanup, and bytes
  remain separate tasks;
- moving to a broker, server-side merging, or multiple server heads will require a
  new ADR with measured justification.

## Reconsideration Conditions

The decision will be reconsidered if measured load requires independent delivery
outside PostgreSQL, if supported devices need retained history that cannot be stored
in the ledger, or if a demonstrated scenario arises where explicit client-side
merging cannot provide acceptable UX without data loss.
