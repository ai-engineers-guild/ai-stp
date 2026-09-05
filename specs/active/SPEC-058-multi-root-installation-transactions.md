---
description: "SPEC-058: Recoverable consumer coordination of one setup across multiple provider roots."
last_verified: "2026-09-05"
---

# SPEC-058: Multi-root installation transactions

## Purpose

Install one exact setup across every required target scope without false
all-or-none claims and with deterministic recovery after any interruption.

## Scope

Included: local durable transaction identity and state, exact child plans,
canonical scope order, one confirmation, sequential application, compensation,
resume, recovery, and machine-readable status. Excluded: a new provider command,
instantaneous filesystem atomicity, direct target writes by ai-stp, distributed
locks outside the selected roots, and automatic privilege expansion.

## Terms

- Multi-root transaction — one consumer record binding two or more
  scope-specific provider operations for one exact SetupVersion.
- Child operation — an ordinary protocol-v3 installation operation owned by
  one transaction and one target scope.
- Compensation — exact provider restore of a child root from the BackupRef
  produced by its applied operation.

## Requirements

- `REQ-5801`: Planning resolves at least two distinct supported scopes, compiles
  one bundle and obtains one pure provider plan per scope before creating a
  transaction. The canonical order is global, user_root, project. Duplicate
  scopes are rejected. Targets are identified by canonical physical root, not
  by scope label: the same directory, a symlink or case alias of it, and an
  ancestor or descendant of it are overlapping and refused.
- `REQ-5802`: The transaction digest binds the exact setup passport, ordered
  scopes, canonical targets, bundle identities, provider release identities,
  provider plan digests, expected target digests, effects and rollback actions.
  Repeating identical input returns the same open transaction; changing one
  bound field changes the digest.
- `REQ-5803`: One confirmation approves the transaction digest and every child
  plan digest together. Before confirmation no provider mutation command runs.
  An expired, stale, independently approved, or independently changed child
  blocks the transaction without effect.
- `REQ-5804`: Apply invokes child operations only in canonical order and records
  each transition durably. verified requires verified postconditions from all
  children. A timeout or lost process never causes blind re-application.
- `REQ-5805`: On a refused, failed, partial, or unknown child result, the consumer
  settles its provider journal and compensates every possibly changed child in
  reverse order using its exact target-bound BackupRef. Compensation is
  idempotent.
- `REQ-5806`: Terminal outcomes are verified, rolled_back, and cancelled.
  recovery_required is non-terminal and lists every unsettled child with its
  last accurate state and next action. No failed or rolled_back outcome is
  emitted while a root may still contain an unverified effect. cancelled means
  no native effect was made.
- `REQ-5807`: While a transaction is active, its children cannot be independently
  approved, cancelled, applied, or resumed through the public command surface.
  Status remains read-only. A new transaction whose physical roots overlap an
  active reservation — same root, alias, ancestor, or descendant — is rejected
  before provider planning. Two processes opening the same registry cannot both
  hold overlapping roots.
- `REQ-5808`: Transaction records contain no target bytes, BackupRef bytes,
  credentials, environment values, or absolute paths in ordinary machine output.
  Providers remain the sole writers and backup owners.

## States and errors

States are planned, applying, compensating, recovery_required, verified,
rolled_back, and cancelled. Typed refusals distinguish incomplete scope
coverage, duplicate or physically overlapping target, stale child plan, active
target transaction, unsettled provider journal, compensation failure, and
corrupt transaction state.

## Security and privacy

Each child retains the provider release, isolation, path, bundle, and
postcondition checks of SPEC-008. Coordination cannot relax a child refusal or
grant a permission profile. Machine output uses target IDs and scopes rather
than absolute paths.

## Compatibility and migration

This is an additive consumer state machine over protocol v3. Existing
single-scope operations and provider wire bytes do not change. Removing the
feature leaves child operation history and provider backups readable; active
transactions must be recovered before downgrade.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-5801` | A three-scope fixture proves all plans precede confirmation or mutation, canonical ordering, and duplicate rejection. Same-root, symlink-alias, and ancestor/descendant fixtures are refused; sibling directories that only share a name prefix are accepted. |
| `REQ-5802` | Field-by-field mutation changes the transaction digest; identical planning replays one record. |
| `REQ-5803` | Confirmation atomically binds every child; expiry, staleness and independent child mutation produce no provider apply call. |
| `REQ-5804` | Trace and process-kill tests prove ordered apply, durable progress, all-child postconditions and no blind retry. |
| `REQ-5805` | Failure injection at each child restores changed roots in reverse order and repeating recovery makes no second effect. |
| `REQ-5806` | Every interruption point reports only an accurate terminal or recovery state and names unsettled children. |
| `REQ-5807` | Public child mutation commands and overlapping plans are rejected while status remains available. A second process cannot reserve a descendant of an active root. |
| `REQ-5808` | Secret and path fixtures find neither bytes nor absolute paths in SQLite records, logs, or JSON output. |

## Required checks

Run just docs-gen, just docs-check, just back-static, and just back-test.
