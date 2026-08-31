---
description: "Capability-negotiated provider protocol v3 with one planned operation path."
last_verified: "2026-08-09"
---

# ADR-0061: Capability-negotiated provider protocol v3

Status: accepted; the machine model and contract tests are implemented by this decision,
while public provider releases and cross-repository E2E remain mandatory conditions
for production rollout.
Supplemented by `ADR-0085`: the identity of a provider kit is its aggregate digest.

## Context

The frozen protocol v1 and v2 require a single universal set of twelve
commands. This form conflicts with the native boundaries of five providers: Claude Code
does not own software or launch, Codex and Pi intentionally do not remove software, and
`software-plan` is not a commonly implemented capability. Formal
conformance would force a provider to declare fictitious actions or claim
ownership of state owned by another party.

In addition, v1/v2 split setup changes, recovery, and the software lifecycle
across separate wire commands. A prepared and composed setup requires one
verifiable path: immutable `SetupDefinition` → `HarnessBundle` → pure plan →
confirmation of the exact digest → apply under lock. Backup, recovery,
replacement, and removal must have the same plan binding, while the permission profile
must not become the setup identity.

## Alternatives

1. Extend v2 with optional fields. Rejected: v2 has been declared frozen, and
   an old consumer does not know the new semantic constraints.
2. Retain the twelve commands and allow them to return `unsupported`. Rejected:
   this leaves the universal surface normative and allows the absence of a
   capability to be discovered only after the wrong operation has been selected.
3. Introduce v3 with a small mandatory command core and capability-negotiated operations.
   Chosen: the provider reports a truthful closed-world model before plan, and all changes
   pass through a single plan/apply protocol.

## Decision

Protocol v1 and v2 remain unchanged. Protocol v3 divides the surface into
a mandatory setup/bundle boundary and declared capabilities.

The set of commands and operations belongs in `provider-kit/v3/manifest.json` and
is enumerated there, not here: this decision record establishes why the boundary is drawn
this way, not what is currently inside it. A list in the ADR would become
silently outdated because nothing generates it.

The mandatory part consists of the setup/bundle core commands and the operations for materialization,
replacement, copying, recovery, and removal. An optional command is invoked only when
its capability is declared; capabilities for the lifecycle of provider-owned software and
runtime launch are listed in `provider-info`, and the consumer does not invoke
an undeclared operation. Refusal has a stable reason code and occurs before plan
and before any change to the target.

`plan-operation` is pure and returns a canonical provider plan artifact. The plan
binds the protocol/provider release, operation, canonical target and snapshot digest,
an optional exact HarnessBundle, an optional `BackupRef`, a separate permission profile,
platform/runtime identity, expiry, and expected effects. `apply-operation` accepts
the plan itself and its exact digest, acquires the canonical target lock, and rechecks
all preconditions after locking. A timeout or malformed response after a possible
effect means `partial`, not permission for a blind retry.

Before mutation, the provider publishes a durable target-local `prepared` journal
bound to the exact plan and a target-bound `BackupRef`; after verifying the result, it
publishes `committed`. Any incomplete journal/transaction/backup staging
blocks a clean plan. `recover-operation` is a separate confirmed mutation
boundary: the `prepared` phase is restored from the exact backup, while `committed` only
verifies the result and completes cleanup. Consumer `resume` reads status first
and may drain this journal, but does not blindly repeat apply.

Prepared and composed setups differ only in the origin of the finalized immutable
`SetupDefinition`. After finalization, they use the same HarnessBundle,
verification, plan, confirmation, application, state, backup, recovery, and removal paths.

`provider-info` contains the build manifest hash and a content-addressed projection profile:
supported component kinds, projection kinds, native identifier namespaces,
collision/ownership rules, bundle formats, limits, OS/architecture, and the profile digest.
The setup compiler builds native operations only from the exact profile, and the provider
independently repeats the validation. An unknown component, surface, operation, protocol,
or profile digest results in closed refusal; silent drop and best-effort conversion are prohibited.
The conversion report also binds the projection kind, and every component must
own non-empty exact native content. Provider-owned validators check
the syntax of native JSON/TOML and required tree markers before plan.

Provider state and BackupRef preserve at least the protocol/provider build and release,
harness/target identity, SetupVersion passport digest, ordered exact component references
and content hashes, SetupDefinition hash, logical bundle and raw artifact hash,
provider plan hash, operation identity, target precondition and native ownership
manifest, previous verified identity, and drift state. Secret values are not
preserved. Read-only `status` never migrates an old stamp: migration
occurs only in a confirmed mutation after a backup.

Network policy remains the truthful model from ADR-0047. Local validation/plan/status and
local apply phases require proven `none` enforcement. Software download
has a separate `artifact_download` phase; the subsequent apply is local again. Launch
declares `runtime_external`.

## Consequences

A public provider can conform to the common protocol without claiming ownership of
host-owned software. Claude Code correctly declares the absence of software/launch;
Codex and Pi declare the absence of software removal. Grok Build and OpenCode may declare
the full software lifecycle only when it is actually implemented.

A new immutable public conformance artifact is introduced: schemas and reference examples,
a hostile corpus, and expected digests. Public providers do not depend at runtime
on the closed authoring environment or private `ai_stp`; they are validated against the exact
published version of the suite, while the closed control plane repeats E2E and promotion checks.

Migration is provider-first. Old standalone stamps are read without
modification; the first confirmed v3 mutation then creates a backup and atomically writes
the new provenance schema. The protocol version and release digest are selected from the verified
provider release manifest before launch and are not upgraded based on a response from an unknown process.
A provider does not declare the digest of an archive that contains the provider itself: the consumer binds
it separately to an independent build digest.

## Reconsideration Conditions

This decision is reconsidered if all supported products acquire identical
native ownership of software/launch, or if the provider process is replaced by a single trusted
runtime with an equivalent capability and isolation model.
