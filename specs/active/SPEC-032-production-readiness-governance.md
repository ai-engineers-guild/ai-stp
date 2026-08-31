---
description: "SPEC-032: Evidence-based production readiness, data governance, abuse protection, and recovery."
last_verified: "2026-08-22"
---

# SPEC-032: Production readiness, governance, and recovery

## Purpose

Before the first production release, the platform proves at an exact commit that
its configuration, observability, data handling, abuse protection, and recovery
are ready for operation. The evidence answers a question about the tree; the
`ADR-0109` pipeline performs deployment—a green `check` advances `deploy/prod`,
and the host fetches that ref.

## Scope

Included: production-configuration validation, safe release evidence, SLO and alert
policy, verifiable data governance, server-side abuse protection, backups, recovery
and rollback rehearsals, operator documentation, and release evidence. Excluded: a
new APM vendor, automatic remediation, automatic blocking based on reports, a browser
control plane, and changes to the CLI or local registry.

Policy fields and wire formats belong to their canonical owners: data—
`SPEC-013`, HTTP/API — `docs/contracts/` and `packages/contracts`, telemetry —
`SPEC-017`, moderation—`SPEC-016`, deployment and recovery—`SPEC-024` and
`docs/operations/runbooks/`. This specification does not duplicate their schema
or state vocabulary.

## Terms

- `Readiness evidence` — a safe, reproducible set of verification results for one
  exact commit, configuration/policy revisions, and environment.
- `Operational policy` — an approved versioned policy for SLOs, alerts, retention,
  or abuse limits; numeric values are not implicit application defaults.
- `Recovery rehearsal` — restoration of a backup to an isolated data copy with a
  verifiable result that is not a production restore.
- `Release decision` — a decision to release a change, made using readiness
  evidence that is still valid. Under `ADR-0118`, the agent makes it within the
  owner's vision and identifies it in the report; it requires no separate human approval.

## Requirements

- `REQ-3201`: A production change is permitted only after successful validation
  of production configuration; a missing required secret, policy reference, safe
  release identity, or unavailable required dependency produces an observable
  failure before traffic is switched.
- `REQ-3202`: Readiness evidence is bound to an exact commit, environment, schema
  revision, and versioned operational policies; it records the outcome, timestamp,
  safe IDs/digests, and named residual risks without secrets, tokens, env values,
  private bytes, or optional personal data.
- `REQ-3203`: A change to the commit, configuration/policy revision, or schema
  revision, or expiration of the permitted evidence lifetime makes the previous
  set ineligible for owner approval and requires it to be collected again.
- `REQ-3204`: The SLO and alert policy are approved before production launch, are
  versioned, and link to a runnable operator response; telemetry covers at least API,
  authentication, dependency/readiness, queue, object storage, publication,
  moderation and rate-limit/abuse signals per `docs/operations/observability.md`.
- `REQ-3205`: An absent or unavailable telemetry exporter does not break the application,
  but a missing required readiness signal, policy, or recorded alert-response prevents
  successful production evidence from being collected.
- `REQ-3206`: Production data governance implements `SPEC-013`: export, logical
  and physical deletion, and audit and backup retention have an approved policy,
  explicit authorizer, safe diagnostics, and verifiable outcome; direct object
  storage access does not become an authorization bypass.
- `REQ-3207`: Rate limits and abuse protection are applied at the server boundary
  before a resource-intensive or sensitive mutation, distinguish safe client classes,
  and do not trust browser state, request headers, or report count as authority.
- `REQ-3208`: An abuse signal, rate-limit rejection, staff read, and staff lifecycle
  action preserve safe correlation/audit evidence. No automated signal blocks,
  hides, deletes, or discloses an object without an existing explicit audited staff decision.
- `REQ-3209`: A recovery rehearsal restores PostgreSQL metadata and RustFS data in
  an isolated environment, verifies readiness and consistency between metadata and
  object storage, includes no secrets or object bytes in the evidence, and does not
  change production data.
- `REQ-3210`: A rollback rehearsal restores the previous exact artifact under
  `deploy lock`, verifies readiness, and performs no destructive schema downgrade;
  on incompatibility, it preserves evidence of the abort and follows
  `docs/engineering/schema-evolution.md`.
- `REQ-3211`: A release decision relies only on complete, valid readiness evidence:
  an incomplete, rejected, or expired set does not release. The pipeline, not a
  separate human approval, executes the decision (`ADR-0109`, `ADR-0115`,
  `ADR-0118`); the requirement on the operation itself remains unchanged—a plan,
  exact digest, repeated precondition validation, and idempotency, providing a
  machine guarantee that exactly the approved effect is executed.
- `REQ-3212`: Operator instructions and release evidence link every mandatory
  readiness check to a command, expected result, recovery instruction, and owner;
  an unperformed check and residual risk are recorded explicitly rather than
  represented as success.
- `REQ-3213`: Safety validation has bounded telemetry for queue wait/run/requeue,
  scan count/cache/latency buckets and each check result/duration; offline
  benchmark records the commit, policy, corpus, profile, and absence of network/CLI,
  and measured latency is not presented as a universal cross-machine SLO.
- `REQ-3214`: Every component kind and setup has 10 to 20 relevant malicious
  filesystem examples and at least two clean control examples. One sequential
  platform scenario runs them through server-side security checks without network
  access, emits a machine-readable report, and fails on a missed attack or false finding.

## States and errors

Readiness evidence may be `collecting`, `complete`, `rejected`, or `expired`.
`complete` means only that the included checks are complete and successful, not
that production deployment occurred; after its bindings change or it expires, it
becomes `expired`. Errors from specific APIs and operations retain their contracts'
registered `AI_STP_*` codes. An evidence error provides a safe reason for
incompleteness and a recovery instruction without disclosing configuration or data.

## Security and privacy

All production writes require an explicit confirmation step within the operation—
`confirm` with the exact digest of the saved plan, not human approval: this
guarantees that exactly the planned effect is executed. Evidence, alerts, logs,
traces, and audit use an allowlist of fields and contain no secrets, session data,
private object bytes, raw diagnostics, full local paths, or environment values. A
backup remains a protected data asset and is not published as evidence. Abuse
limits do not become hidden profiling, a means of discrimination, or automatic
moderation; staff authority and data access remain minimal and auditable.

## Compatibility and migration

Readiness evidence and policy references are added additively. Existing API clients
must not require new fields before an agreed rollout. A new policy revision does
not rewrite historical evidence; it makes it ineligible for the next approval if
it changes an applicable check. New telemetry and abuse controls are first verified
with a recorded outcome; production rollout remains owner-approved.

## Acceptance criteria

| Requirement | Executable verification method |
| --- | --- |
| `REQ-3201` | Configuration validation rejects a missing secret, policy reference, release identity, or dependency before traffic switch. |
| `REQ-3202` | The evidence fixture contains only permitted identifiers/outcomes and fails on a secret, token, env value, or private bytes. |
| `REQ-3203` | Changing each binding or expiration makes previous evidence ineligible for approval. |
| `REQ-3204` | Policy validation proves a versioned SLO/alert policy and runnable response for every required signal class. |
| `REQ-3205` | The application starts with an unavailable exporter, but the readiness-evidence check fails without the required signal/policy/response. |
| `REQ-3206` | The integration matrix covers export, tombstone, purge, audit/backup retention, and denial of direct object-store access. |
| `REQ-3207` | API tests prove server-side limits for anonymous/authenticated/sensitive paths and no client-side bypass. |
| `REQ-3208` | Audit/redaction validation records abuse and staff events; N abuse signals do not change lifecycle without a staff action. |
| `REQ-3209` | An isolated rehearsal restores PostgreSQL and RustFS, passes readiness/integrity checks, and does not change the production fixture. |
| `REQ-3210` | The rehearsal verifies deploy lock, exact artifact rollback, readiness, and absence of destructive downgrade. |
| `REQ-3211` | A negative check proves that CI/agent/automation without explicit approval does not cause a production mutation. |
| `REQ-3212` | The release-evidence inventory links required checks to a command, outcome, owner, and recovery instruction. |
| `REQ-3213` | Unit tests verify the bounded metrics snapshot, while `just safety-benchmark --iterations 3 --concurrency 1` emits deterministic offline evidence with `network=disabled`, case order, and scan/check/queue metrics. |
| `REQ-3214` | `just safety-corpus` reads the versioned manifest, sequentially verifies every file fixture and setup pin scenario, and records per-kind counts, recall, false-positive rate, and the mismatch list; the scenario test requires complete detection of manifest expectations with no findings in clean controls. |
