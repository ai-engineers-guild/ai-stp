---
description: "States, plan, journal, and recovery of a mutating operation."
last_verified: "2026-08-09"
---

# Mutating operation

## States

```text
planned
approved
applying
applied_unverified
verified
failed
partial
stale
cancelled
rolled_back
```

Transitions occur only on explicitly permitted events. A terminal state is
durably recorded before responding to the caller.

## Plan

The immutable plan contains the operation identifier, action type, expiration,
author, target entity, expected target revision or hash, schema, provider, and
provider protocol versions, the absolute provider target for the isolated v2
call, the canonical signed release manifest for the trusted path, the effect
list, confirmation requirements, the plan hash, and the recovery action.
An old schema v1 plan does not change its digest after migration; new schema v2
includes protocol and target in the confirmation scope.
New schema v3 also includes the release manifest: changing the signature,
sequence, or digest after displaying the plan requires new confirmation.
Schema v4 separately binds explicit provider release recovery to the same
confirmation: ordinary target rollback does not permit an older provider
artifact, while recovery requires an exact digest from local verified history.
Schema v5 binds the complete HarnessBundle and the single-writer plan: format,
logical hash (`bundle_digest`), byte-for-byte artifact hash, size, and provider
plan hash (`provider_plan_digest`). The absolute cache path is derived and is
not included in the digest. Old schemas v1–v4 retain their historical identity,
but a new effect without exact bundle bytes and a provider plan is prohibited
under them.

A change to any precondition makes the plan stale. Confirmation applies to the
exact plan hash and does not carry over to a new plan.

## Journal

Each step creates an event with a sequential number, idempotency key, time,
state before and after, safe result, and evidence reference. The event stream is
append-only. Secrets and original private content are not recorded.

## Application

Permissions, expiration, plan hash, and current target are rechecked before the
first effect. After an effect but before result verification,
`applied_unverified` is used. State `verified` is set only after durable
verification of every mandatory postcondition and is the sole name for success.
The mapping of provider states is described in `provider-protocol.md`.

The raw digest and size of the exact cached HarnessBundle are rechecked before
calling the provider. `apply-bundle` receives the provider plan digest, not the
`ai_stp` plan digest; the two values are distinct, and both are covered by user
confirmation. A response without exact echoes of the bundle, target, and
provider plan after a possible effect moves the operation to `partial`.

Together with `verified`, the target state observed after the effect and the
setup version installed by the operation are recorded. The observation is read
anew after the effect rather than copied from the plan: a value captured before
the write can report only “nothing changed.” This pair later distinguishes local
drift from an untouched target and provides the exact previous version for
rollback.

Verified-history order is defined by an explicit monotonic `global_sequence` of
terminal events in the local registry, not by wall-clock timestamps alone or by
operation identifiers. The number is assigned under a write lock; two operations
may finish in the same millisecond, while an operation id reflects creation, not
completion. Rollback selects the record immediately before the latest terminal
event and therefore does not reverse direction on a timestamp tie.

## Partial result

An unknown effect, a failure after a write, or a rollback error creates
`partial`. Such an operation is not retried automatically. The recovery report
contains the last confirmed state, effects already performed, a backup
reference, and permitted next actions.

An operation whose process was lost before result verification completes by
rechecking postconditions, not by reapplying: repeating the effect is prohibited,
not observing the target. The check asks the provider for the current target
state and records the response—`verified` if the postconditions hold, otherwise
`partial`. An operation left in `applying` passes through `applied_unverified`:
the provider was called, and “an effect may have occurred” is the only honest
name for this condition. Without this path, an interrupted operation cannot be
resolved: cancellation after a possible effect is prohibited, while reapplying
is a prohibited repetition.

## Retry and cancellation

A retry with the same key returns the existing operation while it remains
active. After a terminal outcome, the same logical request creates a new
operation and does not reopen the old one: the previous journal and plan are
preserved, while allocation of the new operation's internal idempotency key is
serialized by the same write lock. This is especially important for `stale`,
`cancelled`, and `partial`, because none of these states permits a transition
back to application. Cancellation is allowed only before an irreversible effect
or through explicit compensation. Expiration of an external-call timeout does
not prove that no effect occurred.
