---
description: "Hide scan journal entries without destroying immutable observations."
last_verified: "2026-10-11"
---

# ADR-0233: Recoverable scan journal deletion

Status: accepted.

## Context

Administrators need to remove completed scans from the journal. Published scan
observations are immutable and support technology findings and provenance.

## Decision

Store a tenant-scoped deletion marker separate from the immutable scan. Journal,
detail, findings and export reads exclude marked scans. Deletion requires the
same `landscape.manage` policy as the action menu, current authorization revision,
expected revision zero and an idempotency key. Active scans cannot be deleted.
The marker and audit/receipt are written in the same transaction.

## Consequences

Original observations remain recoverable. Restoring visibility requires removal
of the exact deletion marker through an administrator recovery operation; no
public restore endpoint is introduced. Rolling back API/web images leaves the
additive marker table intact. Downgrading the migration removes only markers,
which makes retained scans visible again.
