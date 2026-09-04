---
description: "Implementation sequence for unique public identities, the Git-owned Official registry, recoverable updates, and unified ownership and verification requests."
last_verified: "2026-09-04"
---

# Official Registry, Identity, and Requests Implementation Plan

Normative owners: `SPEC-059`, `SPEC-056`, `SPEC-057`, `SPEC-016`,
`SPEC-038`, `ADR-0149`, and `ADR-0150`. This plan sequences their delivery and
does not replace their requirements.

## 1. Freeze contracts and inventory

1. Add the Official manifest schema and normalization contract to source-owned
   contracts; regenerate machine schemas only after the normative review.
2. Inventory exact upstream coordinates, component roots, kinds, licenses,
   attribution, stable IDs, canonical names, and RU/EN display names for
   Ponytail, Caveman, Grill Me, Context7 MCP, Serena MCP, AI STP Skill, and all
   other intended Official entries. A product name without an exact source is a
   blocked entry, not a partially enabled source.
3. Define additive API models for account handle/display identity, localized
   component names, request topics, and request status. Keep operator decisions
   absent from the HTTP contract.
4. Define stable errors for normalized-name collisions, foreign catalog-line
   ownership, stale ownership revision, manifest mismatch, and sync delivery.

Exit: schemas express every identity, request topic, manifest field, sync state,
and error without requiring a database migration or web release.

## 2. Expand account and catalog identity storage

1. Add normalized account handle and display-name columns without unique indexes;
   reserve the fixed Official ID, handle, and display spelling in the seed path.
2. Add `catalog_identity` and localized RU/EN presentation rows. Backfill one
   proposed current owner and canonical name per component stable ID from
   existing catalog metadata without changing immutable passports.
3. Produce deterministic account-name, component-name, and mixed-owner conflict
   reports. Stop rollout if any conflict remains; do not auto-rename or merge.
4. After operator resolution, add database uniqueness and foreign keys, then
   switch publication planning and execution to the catalog-line owner and
   ownership revision.
5. Repeat ownership validation in the final publish transaction so plans made
   before a transfer cannot commit afterward.

Stage result: all current data is readable, every new account and component line
is unambiguous, and a foreign publisher cannot extend an owned stable ID.

## 3. Introduce the repository-owned Official manifest

1. Add one checked-in manifest containing the complete enabled and disabled
   Official inventory and its schema version.
2. Validate global stable ID/canonical-name uniqueness, RU/EN name uniqueness,
   fixed Official identity, source safety, attribution, license observation,
   projection target, and update policy before accepting the file.
3. Implement an idempotent reconciler from one exact manifest revision to
   PostgreSQL source rows. Record additions, material changes, disablement, and
   removal in the audit log.
4. Import existing production source rows only when they match an exact manifest
   entry. Report and stop on undeclared or ambiguous rows.
5. Remove direct production creation of Official source rows; retain a read-only
   status and validation command for operators.

Stage result: a checkout answers exactly what is Official, and production source
state is a reproducible projection rather than an independent inventory.

## 4. Make update delivery recoverable

1. Expand the Official sync table into the domain ledger and add the closed
   states, safe error fields, attempt count, retry time, exact source revision,
   provenance, publication plan, job ID, and terminal timestamps.
2. Add the minimal transactional outbox. Scheduling commits sync attempt and
   outbox event together; dispatch inserts into the existing PostgreSQL job queue
   under a unique idempotency key.
3. Map worker retry and DLQ outcomes back to the domain ledger. Preserve the last
   published version on fetch, validation, dispatch, and publication failures.
4. Add one reconciliation pass for due-without-attempt, attempt-without-outbox,
   outbox-without-job, missing/stale job, unrecorded completion, and unrecorded
   DLQ. Repair through ordinary idempotent paths and audit each repair.
5. Expose read-only operator status by source and attempt plus an audited manual
   retry that cannot bypass disabled, removed, or transferred state.

Stage result: every due update is visible as pending, running, retrying,
dead-lettered, successful, unchanged, or explicitly cancelled; process death at
any handoff has one deterministic recovery path.

## 5. Make transfer an atomic database operation

1. Remove `author_verified` and non-Official restrictions from request creation;
   keep authentication, idempotency, evidence bounds, and rate limits.
2. Replace HTTP ownership approval with one database-bound operator operation
   referenced by case ID, expected current owner, expected ownership revision,
   recipient account, reason, and operator identity.
3. In one transaction, update the catalog-line owner, append ownership and audit
   revisions, mark the source transferred/disabled, clear future scheduling,
   cancel pending outbox and queued work, mark running attempts for cancellation,
   and resolve the case.
4. Fence resolver and publisher work by expected Official owner and ownership
   revision. A job crossing the transfer transaction stops as
   `cancelled_transferred` before catalog mutation.
5. Add the parallel database-bound verification operation. It appends an audit
   revision and updates `author_verified`; request submission itself never does.

Stage result: transfer has one commit point, no later Official update can cross
it, history stays immutable, and verification remains a separate manual fact.

## 6. Unify Web and CLI requests

1. Extend the shared request contract with component complaint, author
   complaint, ownership transfer, verification request, and other. Require a
   custom subject only for other and topic-specific targets only where needed.
2. Update the web report form with RU/EN labels and validation, target prefill
   from component/author pages, and stable English wire codes. Do not translate
   authored text.
3. Extend the existing CLI report preview/confirm/list flow instead of adding a
   second request client. Preserve exact local payload, digest, idempotency key,
   lost-response recovery, bounded evidence, and localized human output.
4. Let staff read and triage every topic in one worklist. Do not expose transfer
   or verification decisions through staff HTTP routes or CLI commands.
5. Keep the anonymous complaint intake only for anonymous complaint use cases;
   ownership and verification requests require an account that can become the
   referenced subject or recipient.

Stage result: Web and CLI create the same private cases, any authenticated
account including Official may request transfer or verification, and only the
database-bound operator path changes authority.

## 7. Rollout and cleanup

1. Deploy additive schema and dual reads before constraints or owner fencing.
2. Resolve migration conflicts, enable unique indexes, and activate catalog-line
   ownership checks.
3. Import and reconcile the Official manifest, then enable outbox dispatch and
   domain reconciliation while the previous scheduler is disabled in the same
   release transition.
4. Enable transfer fencing before accepting the expanded ownership topic.
5. Switch Web and CLI to the expanded request contract, retain compatible object
   report reads, and remove obsolete ownership-claim mutation routes after the
   compatibility window.
6. Update runbooks for manifest rollout, identity conflict resolution, sync
   ledger inspection, DLQ retry, reconciliation, transfer, verification, and
   rollback.

Exit: no active write path can create an ambiguous identity, undeclared Official
source, mixed-owner catalog line, lost update handoff, or post-transfer Official
version.

## Minimum test matrix

| Slice | Mandatory evidence |
|---|---|
| Account identity | Exact, case, whitespace and Unicode-equivalent collisions; concurrent allocation; protected Official identity. |
| Catalog identity | One owner per stable ID; canonical and RU/EN name collisions; stale and foreign publication. |
| Manifest | Required baseline, exact source review, deterministic projection, undeclared-row refusal, add/change/disable/remove. |
| Delivery | Atomic attempt/outbox, duplicate dispatch, retry, DLQ, process death at each handoff, and reconciliation repair. |
| Transfer | Unverified and Official requests, atomic owner/source/job cutoff, running-job fence, idempotent replay, immutable history. |
| Verification | Request without mutation, audited database grant/revoke, no HTTP decision route. |
| Web | RU/EN topic labels, target prefill, topic validation, original authored text, and staff worklist. |
| CLI | Preview/confirm/status, RU/EN human output, stable JSON, idempotent retry, and lost-response recovery. |

## Explicitly deferred

- automatic maintainer verification or automatic ownership approval — until a
  source authority supplies a trustworthy machine-verifiable protocol;
- fuzzy/confusable-name scoring beyond the canonical normalization contract —
  until measured impersonation remains after exact normalized uniqueness;
- a second message broker or workflow engine — until the existing PostgreSQL
  queue and reconciliation fail measured availability or throughput objectives;
- automatic translation of user-authored request text — moderation sees the
  submitted text and locale.
