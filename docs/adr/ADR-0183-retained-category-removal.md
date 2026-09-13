---
description: "Retain category identities and classifications across dictionary removal and restoration."
last_verified: "2026-09-12"
---

# ADR-0183: Retained category removal

Status: accepted.

## Context

Issue #207 requires dictionary CRUD, stable identifiers and historical recovery.
Physical category deletion would destroy classification history or fail its
retained foreign keys; replaying the seed could also undo an owner's removal.

## Decision

Remove a category by archiving its existing identity. An additive active/archived
state belongs to category metadata, not technology lifecycle or canonical links.
Retain its name reservation, classifications, provenance and safe audit history.
Existing assignments may remain; new assignments require an active category.
Restoration is an explicit authorized, revision-guarded mutation of the same row.
Seed replay does not change state. Optional additive wire state permits old
snapshots to remain readable without inventing their state.

## Consequences

Deploy the additive state column and constraint before new routes. Application
rollback retains the column, archived identities and classification history;
it does not physically delete or implicitly restore categories. Any destructive
retention policy requires a separate specification and verified recovery backup.
