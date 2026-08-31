---
description: "Decision for ai_stp to own the domain model and delegate target writes to public NDDev providers."
last_verified: "2026-08-03"
---

# ADR-0002: Own the core and use public providers

Accepted on 2026-08-03.

## Context

External package-management and distribution tools do not cover a coherent model for passports, the project index, arbitrary setup composition, device synchronization, and the secure lifecycle of five harnesses. A mandatory dependency would give an external project control over key contracts.

Public NDDev managers already implement explicit target directories, backup, recovery, software lifecycle, and launch for their harnesses.

## Decision

`ai_stp` owns passports, the registry, the project index, the setup graph and compiler, trust and access decisions, synchronization, and provider orchestration.

The public provider for a specific harness owns the native target, runtime installation and updates, locking, staging, backup, apply, launch, state, and recovery.

The closed setup-system authoring circuit remains an internal validation/release control plane and is not part of the distribution. It is named here as a role rather than a repository: the repository changed during these two years, while the boundary did not.

## Consequences

Five public repositories receive an additive versioned provider protocol. APM/SX may appear only as optional adapters without ownership of core data or the final target.
