---
description: "One ai-stp product and Rust CLI, with separately released setup components behind the existing provider boundary."
last_verified: "2026-10-10"
---

# ADR-0228: Setup systems are ai-stp components

Status: accepted; native writable lifecycle and production cutover remain pending.

## Context

The owner requests one product operated through the Rust ai-stp CLI while
retaining the setup-system repositories. The native runtime already acquires
authenticated provider executables and invokes their read-only services without
a separate user installation. Separate source and release repositories need
not create separate user workflows.

## Decision

- Setup systems are managed installation components of ai-stp. The eventual
  public entry point is `ai-stp`; `ai-stp-v2` remains the isolated Rust preview.
- Keep the existing source workspace, seven public repositories, package names,
  publisher identities and immutable releases. Repository ownership, licenses
  and access do not change. A product boundary is not a repository transfer.
- Keep provider protocol v3 and the isolated provider process. The CLI owns
  selection, acquisition, exact plans and operation history; the component
  remains the sole writer of its harness state and owns filesystem recovery.
  Linking its mutation kernel into the CLI would create another writer and
  remove an established isolation boundary; this is not required for one CLI.
- A new request may omit the component version. Resolve it from one exact
  release selected by the ai-stp build before planning or acquisition. Explicit
  exact overrides remain available. Record the resolved release in plans and
  results; never resolve defaults while applying or replaying a stored plan.
- A selected release is not trust evidence. All paths retain publisher,
  attestation, platform, digest, rollback-floor and process-isolation checks.
  Failure never falls back to an executable on `PATH` or a floating release.
- Provider expert commands and historical package entry points remain
  compatibility and maintenance interfaces during migration. Their retirement
  requires consumer evidence; new user journeys belong to ai-stp.

## Delivery and consequences

The first slice implements managed release selection for new native provider,
selection, matrix and composition requests. It does not authorize target writes.
The code-adjacent CLI contract and executable registry own implemented behavior.

C4 must finish durable exact-plan software/configuration apply, independent
verification, interruption recovery and active-target handoff. C6 owns coordinated
attested releases and consumers; C7 owns the default executable and legacy CLI
retirement. Their acceptance criteria stay in the existing implementation roadmap.
Do not create automatic backups; preserve existing recovery references and use
ordinary transaction/activation state under ADR-0227.

Changes ship separately in the CLI and component repositories with exact-SHA
checks. A managed pin advances only after all declared component journeys pass.
An unpromoted slice can be reverted through Git; completed plans retain their
original release identity. Production rollback still follows ADR-0227's
current-state compatibility rule.

## Revisit conditions

Revisit the process boundary only if measured evidence requires a replacement
that preserves one writer, confined authority, exact provenance and recovery.
Neither a shared product name nor startup optimization alone removes those
requirements.
