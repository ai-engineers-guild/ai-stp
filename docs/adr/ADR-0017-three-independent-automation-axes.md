---
description: "Decision to separate the execution profile, validation isolation, and mutation integrity."
last_verified: "2026-08-04"
---

# ADR-0017: Three independent automation axes

Status: accepted. Supersedes `ADR-0006`.

## Context

`ADR-0006` established that all managed MVP targets use the full automatic-access profile and that sensitive actions require an explicit user decision. The decision is correct, but its wording permits two opposite misreadings.

The first is that “full automatic access” is read as a promise to remove confirmations everywhere, including the plan, backup, and artifact-integrity verification. The second is that statements about safe installation, the restricted local environment for checks, and numerous confirmations are read as a requirement to restore sandboxing and permission prompts within the harness itself.

The reason is that three different things were described with one vocabulary: how the agent operates inside the harness, how validation tools are run, and how a mutating control-plane operation is performed.

## Options

1. Retain one formulation and refine it in every document. This is inexpensive, but divergence will return with the first edit.
2. Abandon the full automatic-access profile. This contradicts the selected product behavior and does not resolve the mixing of axes.
3. Explicitly separate three independent axes and give each its own name and owner.

## Decision

Option 3 is accepted. Three independent axes are defined; the same word means different things on different axes.

```text
runtime_profile          full-auto
  how the agent operates inside the harness
  the only profile in the MVP
  mapped to the provider's native setting

validation_isolation
  how ai_stp runs external validation tools
  an internal execution boundary, not a user mode
  argument array, shell=false, environment, time, output limit

mutation_integrity
  how a mutating operation is performed
  inspection, plan, exact hash, lock, backup,
  revalidation, application, result verification, journal, rollback
```

**The execution profile does not waive integrity.** The `full-auto` value applies only to the first axis. It does not waive permission checking, artifact verification, the plan, confirmation of a sensitive action, backup, atomicity, or recovery.

**Validation isolation is not a user mode.** The restricted environment for running tools is an `ai_stp` implementation detail, not a sandbox that the user enables or disables.

**The list of sensitive actions is retained.** Public publication, a new major version line, installation of an object from an unverified author, system-privilege escalation, complete data erasure, deletion of a target or backups, and external Git and deployment actions require an explicit user decision.

**Native settings are described as provider capabilities.** The mapping of a profile to specific native harness flags belongs to `provider-info` and the capability matrix, not to an enumeration in the core. Vendor flag names change and do not become part of identity.

**Future profiles remain an extensibility option.** Only `full-auto` is implemented in the MVP; other profiles may be agreed later without changing the second and third axes.

## Consequences

- `ADR-0006` gains superseded status and links here;
- `docs/product/scope.md`, `SPEC-011`, `SPEC-014`, and `SECURITY.md` use the axis names instead of a general statement about security;
- `contracts/provider-protocol.md` describes mapping the profile to native capabilities through `provider-info`;
- documentation validation rejects a claim that full automatic mode waives the plan, permissions, or artifact verification;
- a contract fixture maps each supported harness to its native profile setting.

## Reconsideration conditions

The decision shall be reconsidered if a supported harness emerges without a native equivalent of the full automatic-access profile, or if users begin demanding a second execution profile before completion of the MVP.
