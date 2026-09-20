---
description: "Deterministic install/update planning over effective corporate assignments."
last_verified: "2026-09-20"
---

# ADR-0196: Corporate assignment plan

Status: accepted. Extends ADR-0194 and ADR-0195.

## Context

Milestone 6 issue 214 lets the CLI - including a CLI running in CI - answer
"what should this user, project, technology, and harness have?" The answer has
to be one machine-readable plan the CLI, Web, and provider agree on, computed
from the same precedence and eligibility rules as the effective-assignment
read, and it must never be a second place where scope policy lives or a write
path into a live harness target.

## Decision

One generated request/response pair: `planCorporateAssignment` evaluates every
catalog line carrying an assignment applicable to the named context -
organization, the member's active teams, the optional project and technology,
and the employee - plus every exact coordinate the caller reports as
materialized. Evaluation reuses the effective-assignment precedence of
ADR-0194, including harness conditions, explicit employee exceptions, and
`latest` resolution against the employee's eligible published versions.

Per line the plan reports the effective state (`assigned`, `revoked`,
`unassigned`), the winning source scope and subject, the resolved exact
version and digest (never `latest`), the caller-reported installed coordinate,
and one outcome with one action: `missing`/`install`, `installed`/`none`,
`outdated`/`update`, `conflicting`/`update` for a same-version digest
mismatch, `unsupported`/`none` when no eligible published version satisfies
the assignment, and `revoked`/`unassigned` with `remove` when the coordinate
is materialized but not allowed. Items are sorted by catalog line and carry no
wall-clock field, so identical policy and materialized inputs produce an
identical plan.

Materialized state is caller-reported input, not server truth: the CLI
collects the provider-verified coordinates for the local target and explicit
`--materialized` entries, sends them in the request, and renders or hands off
the returned plan. The plan endpoint is a read: it writes no assignment,
distribution, audit, or provider-owned state, and applying a plan remains the
existing install transaction with its own approval and durable record.

## Consequences

The API gains an additive plan route and the contracts gain additive plan
models; the CLI gains a `corporate assignment plan` command that consumes the
same contract and never reimplements precedence or classification. Exact
resolved coordinates in plan items are the values `install` consumes, so the
handoff preserves versions and digests end to end. Tests cover deterministic
ordering, every outcome/action pair, `latest` resolution, employee exception
and revocation handling, tenant isolation, and the no-mutation guarantee.
Rollback disables the plan route and CLI command while retaining assignment
and distribution history.
