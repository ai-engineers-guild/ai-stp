---
description: "Idempotent, observable bulk distribution of corporate assignments."
last_verified: "2026-09-19"
---

# ADR-0195: Bulk corporate distribution

Status: accepted. Extends ADR-0194; extended by ADR-0196.

## Context

Milestone 6 issue 206 needs a team or other corporate-scope assignment to be
previewed and distributed across its affected members and projects. The
operation must preserve individual exceptions, explain partial outcomes, and
remain safe to retry. A bulk operation must not become a second assignment
policy or a provider-owned installation path.

## Decision

Represent a bulk request as an explicit assign or revoke action over one source
assignment and a resolved target set. The request carries the existing expected
revision, authorization revision, and idempotency key, and exposes `dry_run`.
Dry-run expands the affected members and projects, exclusions, individual
overrides, and planned per-target results without a durable mutation.

For an applying request, resolve and authorize every target inside the owning
tenant, then reuse the existing single-assignment mutation primitives. The
source assignment remains the policy; per-target distribution records are
derived state keyed by source assignment, target, and operation revision. They
never copy policy fields or grant access. Existing higher-precedence individual
exceptions and revocations remain authoritative.

Return one durable result per target: `applied`, `skipped`, `conflicted`,
`denied`, or `failed`. Target-local success is retained when another target
fails, and every non-success result remains visible with a safe diagnostic.
Retries reauthorize and use the existing idempotency receipt plus the
source/target operation identity to return the original results without
creating duplicate assignments, distribution rows, or audit events.

Expose the resulting per-target distribution state through the generated
contract used by Web, CLI, and CI. The state is `pending`, `installed`,
`outdated`, `failed`, or `revoked`. Distribution observes and reports provider
state; it never silently rewrites an active harness target.

## Consequences

The API and storage gain additive bulk-request, per-target-result, and derived
distribution-state records. Authorization, revision, idempotency, audit,
effective-assignment, and generated-contract code remain shared with the
single-assignment path. Tests must cover dry-run no-op behavior, every target
scope, exception preservation, tenant isolation, partial failure, retries, and
state retrieval. Rollback disables bulk routes and consumers while retaining
the source assignment history and any auditable operation results.
