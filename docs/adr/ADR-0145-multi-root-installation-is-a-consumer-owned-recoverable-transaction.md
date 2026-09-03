---
description: "Decision to coordinate multiple scope-specific provider operations as one recoverable consumer transaction."
last_verified: "2026-09-03"
---

# ADR-0145: Multi-root installation is a consumer-owned recoverable transaction

Status: accepted.

## Context

A setup may have adaptations for global, user_root, and project, while provider
protocol v3 deliberately plans and applies one target and one projection profile
at a time. A single setup installation therefore may require several independent
filesystem roots.

No portable filesystem primitive atomically renames an arbitrary set of
directories, and the roots may be on different filesystems. Describing the
operation as instantaneously atomic would be false. Extending every provider
with prepare, commit, and abort would not remove the interval between commits
and would break the closed provider wire without buying that property.

The existing provider contract already has the primitives the consumer needs:
pure planning, exact target preconditions, a durable single-root journal,
target-bound BackupRef, status, restore, and recovery after an unknown result.

## Decision

ai-stp owns a recoverable multi-root transaction above unchanged provider v3
operations.

The consumer resolves all required scopes first, orders them canonically as
global, user_root, project, and obtains an exact non-mutating provider plan for
every root before asking for one confirmation. The transaction digest binds the
setup, every scope, target, bundle, provider release, provider plan, expected
target digest, and rollback action.

After confirmation, the consumer applies the child plans in canonical order. It
does not report transaction success until every child has a verified
postcondition. If a child fails or has an unknown result, the consumer first
settles that provider's durable journal, then restores every already changed root
from its exact BackupRef in reverse order.

The externally visible guarantee is **all verified or recovery required**, not
instantaneous cross-root visibility. A transaction is verified only when every
root reached its intended postcondition. It is rolled_back only when every
possibly changed root is proven restored. Otherwise it remains recovery_required
and names the unsettled roots; it never claims that nothing happened.

One active transaction owns its child operation IDs. A child cannot be approved,
cancelled, applied, or resumed independently through the public CLI while that
transaction is active. Replaying plan, apply, or recover is idempotent against
the same transaction identity.

## Consequences

- Provider protocol v3 and its release order do not change.
- Providers remain the only writers of each native root.
- Cross-root failure can be observed temporarily, but cannot be reported as
  success and has a deterministic compensation path.
- A lost consumer process resumes from durable child operation and transaction
  state rather than repeating an uncertain effect.
- A setup needing only one scope continues through the existing single-root
  command; the coordinator adds no second path for that case.

## Reconsideration conditions

Reconsider if every supported platform provides one proven primitive for an
atomic exchange of all selected roots, or if a future provider operation owns
all roots itself and can prove that stronger postcondition.
