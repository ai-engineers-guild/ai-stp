---
description: "Recover a rollback's component coordinates from the prior verified bundle, or leave them unknown."
last_verified: "2026-09-26"
---

# ADR-0216: Rollback provenance from the journal

Status: accepted. Implemented behavior is recorded in SPEC-093 and SPEC-094.

## Context

A restore plan carries no install bundle. The provider protocol forbids sending one. Corporate installation facts, inventory, and native usage hooks all need the setup and component coordinates of the bytes that were put back. The rollback row's `backup_ref` is the backup taken before the restore, not the backup that was selected. Reading provider backup slots, or parsing a setup out of a backup label, would cross the provider boundary and invent identity.

## Decision

The selected backup reference is taken from the digest-checked cached provider plan. Provenance is accepted only when one verified capturing operation, the same corporate binding, and the same target agree on that reference, on the native capture digest, and on the managed target digest of the latest verified mutation before the capture. An install or update supplies its cached bundle, including standalone component bindings. A prior rollback is followed by the same rule, with a hop limit. A removal, any mismatch, ambiguity, a partial or cross-account mutation, a missing artifact, or a cycle yields no bundle. Callers then leave the fact incomplete, the inventory scope incomplete, or drop the native observation. Facts that were already delivered stay as delivered.

A plan records the scope it was planned against when that scope is `global` or `project`. The column stays outside the plan digest. A corporate binding with no bundle reads the recorded scope. A bundle that names `global` or `project` still supplies the binding scope. `user_root` is left unrecorded, and the binding stays unknown. Apply and later status still read the scope the plan was made for: the bundle manifest when one exists, otherwise the projection digest sealed in the cached provider plan. That is what keeps a sourceless `project` or `user_root` restore from being compared with the home digest and marked stale.

## Consequences

Restore plans still omit install-bundle fields. Local registry migration 50 adds nullable `operation_plan.target_scope`. Rows from before that column stay null, so a sourceless binding for them remains unknown. An existing binding and a delivered fact stay as written. Historical rollbacks whose digests do not line up remain incomplete, including a capture whose precondition drifted from the previous verified digest. New undelivered rollbacks pick up coordinates on the next projection.

## Revisit conditions

Revisit if a provider plan stops binding the selected backup reference and the native restore digest in the cached artifact.
