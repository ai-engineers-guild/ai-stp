---
description: "Decision to own the AI STP Official inventory in Git and reconcile it through a durable outbox, queue, ledger, and transfer fence."
last_verified: "2026-09-04"
---

# ADR-0150: Git-owned Official registry and recoverable synchronization

Status: proposed.

## Context

Official upstream source rows currently exist only in PostgreSQL. A checkout
cannot answer which third-party components AI STP curates, and a missing daily
enqueue or a lost handoff between source state and the worker queue is not
independently reconstructible. The generic queue has retries and dead letters,
but it is not the domain history of one source update.

Ownership transfer changes catalog rows without fencing the corresponding
Official source. A job created before or after transfer can therefore publish a
later version from AI STP Official unless every publication revalidates current
ownership.

## Options

1. Keep PostgreSQL as the only inventory and add operational runbooks. This
   cannot detect a deleted or omitted source from repository state.
2. Add a second dedicated message broker for Official updates. This duplicates
   the existing PostgreSQL queue without closing the source-to-job gap.
3. Keep a reviewed Git manifest as desired state and project it through a
   transactional outbox into the existing queue, with a domain attempt ledger,
   reconciliation, and an ownership-revision fence.

## Decision

Option 3 is accepted.

A schema-validated manifest in this repository is the canonical inventory of
AI STP Official components. It fixes the Official account identity and, for
every component, the stable ID, canonical and RU/EN display names, kind, exact
source intent, attribution, enabled state, and update policy. PostgreSQL source
rows are the runtime projection of one exact manifest revision. Operators do
not create undeclared Official sources directly in production.

Scheduling creates a domain sync attempt and an outbox event in one PostgreSQL
transaction. An idempotent dispatcher inserts work into the existing job queue.
The queue retains execution retry and DLQ responsibility; the Official sync
ledger records desired, queued, resolving, publishing, successful, retryable,
dead-lettered, and transfer-cancelled domain outcomes. Reconciliation repairs
missing or stale transitions from manifest through terminal outcome.

Successful ownership transfer is one database transaction. It changes the
catalog-line owner, appends ownership and audit revisions, marks the Official
source transferred and disabled, cancels undispatched outbox work and queued
jobs, and fences work already running with the expected owner and ownership
revision. Every publish transaction repeats that fence. Transfer never rewrites
immutable versions and never grants `author_verified`.

## Consequences

- The repository contains a reviewable exact list including Ponytail, Caveman,
  Grill Me, Context7 MCP, Serena MCP, AI STP Skill, and every later Official
  addition; adding or removing a source is a manifest review plus deployment.
- Source availability cannot be guaranteed, but no desired update is silently
  lost: it remains pending, retryable, dead-lettered, or explicitly cancelled
  and reconciliation can derive the next action.
- The existing worker queue and DLQ are reused. The new outbox closes only the
  database-to-queue handoff and is not a second execution queue.
- Disabling, removing, or transferring a source preserves published versions,
  sync attempts, dead letters, and audit history.
- Rollback disables manifest reconciliation and scheduling; it does not delete
  immutable catalog or synchronization history.

## Revisit conditions

Revisit if the PostgreSQL queue cannot meet measured throughput or availability,
if manifests must be delegated to another repository, or if an upstream host
provides a verified ownership-transfer protocol that can replace staff review.
