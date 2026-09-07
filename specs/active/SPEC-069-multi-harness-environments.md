---
description: "SPEC-069: Coordinate separate harness setups within one project environment."
last_verified: "2026-09-07"
---

# SPEC-069: Multi-harness environments

## Purpose

An agent configures several harnesses for one project while each harness keeps
its own setup identity, provider and recovery path.

## Scope

Included: composition of existing exact native plans, complete preservation,
resource overlap detection, aggregate approval, sequential application and
durable recovery. Program and runtime installation retain their own lifecycle
contracts. This is an extension of the SPEC-058 coordinator.

## Terms

Environment transaction means an aggregate of configuration operations for
separate harnesses of one project. Native footprint means the physical paths
covered by a child's digest-bound native capture, not its project-root label.

## Requirements

- `REQ-6901`: The CLI composes at least two exact unapproved native plans for
  distinct harnesses of the same project. Each child retains its own setup,
  provider, scope and plan identity. A repeated harness/scope is refused.
- `REQ-6902`: Composition requires complete capture bindings. Footprints are
  resolved through canonical physical paths; overlapping paths and aliases
  refuse before any target effect. Disjoint harness configuration in one
  project root is allowed. Shared native paths are never silently assigned to
  one harness.
- `REQ-6903`: The aggregate digest binds transaction kind, canonical child
  ordering and every exact child plan. One digest approval approves all child
  plans atomically. Composition performs no provider mutation.
- `REQ-6904`: The coordinator chooses the provider separately for each harness,
  revalidates its bound identity and applies in scope/harness order. Success
  requires verified results from every child and discoverable preserved setups.
- `REQ-6905`: A refused, partial or interrupted child stops forward work. The
  coordinator settles recoverable evidence and compensates possible effects in
  reverse order through each original provider. Unknown outcomes remain
  recovery_required; there is no blind replay or invented successful rollback.
- `REQ-6906`: Native footprints remain reserved while the aggregate is active.
  Alias, ancestor and descendant reservations conflict across processes.
  Transaction-owned children cannot be independently mutated.
- `REQ-6907`: After restarting the CLI, status exposes every harness and child
  setup identity, accurate state and recovery action without target bytes or
  ordinary output containing absolute provider paths.
- `REQ-6908`: Existing single-setup transactions retain their identity and
  semantics. Downgrade cannot silently abandon an active environment operation.

## States and errors

SPEC-058 owns coordinator states. Typed refusals distinguish project mismatch,
duplicate harness/scope, missing complete preservation, overlapping native
resources, stale child plans, unavailable providers and unresolved effects.

## Security and privacy

Child plans retain SPEC-008 release, isolation and permission boundaries.
Composition grants no additional privilege. Resource reservations contain
digests of paths. Providers own target writes and protected recovery payloads.

## Compatibility and migration

The local registry adds a transaction kind. Existing records default to the
single-setup kind and retain their original digest. Environment transactions
bind separate child identities instead of inventing a setup belonging to
several harnesses. Active operations must be settled before downgrade.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-6901` | Different setup versions for two harnesses compose; mixed projects and duplicate harness/scope refuse. |
| `REQ-6902` | Same project with disjoint native files succeeds; shared skills, aliases and nested footprints refuse without apply. |
| `REQ-6903` | Composition invokes no writer; mutation of a child plan invalidates approval; ordering is deterministic. |
| `REQ-6904` | Real providers install distinct native surfaces and each original setup remains selectable. |
| `REQ-6905` | Failure at each child and lost response preserve exact reverse recovery and never replay forward effects. |
| `REQ-6906` | Two registry processes cannot reserve overlapping native resources; independent child writes refuse. |
| `REQ-6907` | Fresh-process status preserves harness/setup identities and accurate recovery actions. |
| `REQ-6908` | Existing multi-root tests and digest fixtures pass after registry migration. |

## Required checks

Run `just docs-check`, `just back-static`, `just back-test` and affected real
provider lifecycle scenarios in isolated targets.
