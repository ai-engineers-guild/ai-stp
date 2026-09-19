---
description: "Deterministic effective corporate catalog assignments and exact install plans."
last_verified: "2026-09-19"
---

# ADR-0194: Effective corporate catalog assignments

Status: accepted. Supersedes ADR-0185; extends ADR-0191.

## Context

Milestone 6 issue 205 needs one corporate assignment workflow to serve
organization, team, project, technology, and employee scopes. An assignment may
follow the current eligible version (`latest`) or name an exact immutable
coordinate. ADR-0185 established exact-version assignments, but its exact-only
object rule does not cover evaluation-time selection, harness conditions, or
effective precedence. Assignment remains distinct from authorization and from
provider-owned installation.

## Decision

Keep one organization-owned assignment store and extend its object to a stable
setup/component line plus an assignment selector. The selector is either an
exact eligible published version (and digest when available) or `latest`.
`latest` is resolved only during an authorized effective-assignment evaluation
or installation-plan operation; the resulting plan records the exact version
and digest. No materialized installation is rewritten when a later evaluation
resolves a different latest version.

Resolve applicable assignments in this order: employee, project, technology,
team, organization. Within one scope, a harness-specific assignment outranks
an unrestricted assignment. An explicit employee exception or revocation
outranks inherited assignments. The effective result includes the winning
assignment identity, source scope, selector, and exact resolved coordinate.

Reuse the existing tenant authorization evaluator, role bindings, revision
guarding, authorization revision, idempotency receipts, audit records, and
retired-history model. Organization-wide and foreign-tenant mutations require
the corresponding explicit scope permission. An assignment never grants
catalog access, changes publication or verification, installs a setup, or
changes active provider-owned harness state.

The legacy exact-version request remains compatible as the exact selector. Web
and CLI use the same generated effective-assignment and plan contracts; neither
client creates a second precedence or resolution algorithm.

## Consequences

Contracts and storage gain additive selector, harness-condition, precedence
explanation, and exact-plan fields. API, CLI, Web, migration, and generated
artifacts must evolve from the existing assignment workflow. Tests must cover
scope precedence, harness-specific selection, user exceptions, latest
resolution, tenant authorization, replay, history, and the absence of live
installation mutation. Rollback disables the new evaluation/planning controls
while retaining assignment history and existing exact assignments.
