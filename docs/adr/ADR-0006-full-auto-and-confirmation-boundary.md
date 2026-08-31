---
description: "Decision to separate full-auto from sensitive actions."
last_verified: "2026-08-03"
---

# ADR-0006: Separate full-auto mode from sensitive actions

Accepted on 2026-08-03. Superseded by `ADR-0017-three-independent-automation-axes.md`: that record preserves this decision and separates execution profile, verification isolation, and change integrity along three independent axes. Read this record only for the context of the original choice.

## Context

Maximum agent authority improves coding workflow efficiency but is dangerous for publication, access changes, data deletion, and system privilege elevation.

## Decision

All managed targets of MVP harnesses use the full-auto access profile. Public publication, creation of a new major version line, installation of an object from an unverified author, privilege elevation, complete data erasure, deletion of a target or backups, and external Git/deployment actions require an explicit user decision.

## Consequences

The runtime profile and confirmation policy remain separate entities. The Agent Skill must ask questions more often while configuring a setup and cannot confirm its own external write.
