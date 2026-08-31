---
description: "Decision on the evidence-based production release barrier: explicit owner approval, data governance, abuse protection, and recovery rehearsals."
last_verified: "2026-08-08"
---

# ADR-0071: Evidence-Based Production Readiness Barrier

Status: accepted.

## Context

By `#187`, the platform already has separate liveness/readiness, safe
diagnostics, structured logs, and OpenTelemetry (`SPEC-017`, `ADR-0039`), private
data and auditing (`SPEC-013`), moderation (`SPEC-016`), and staging deploy, backup,
restore, and rollback (`SPEC-024`, `ADR-0044`). However, these mechanisms do not form
a unified release decision: a single green healthcheck, the existence of a backup,
or a textual runbook do not prove that the production configuration has been verified,
data is governed according to an approved policy, abuse is constrained, and recovery
has actually been rehearsed.

`#187` requires production configuration, alerts and SLO, data retention, export,
and deletion, abuse protection, backups, and full recovery and rollback rehearsals.
At the same time, the issue explicitly prohibits any actions in production without
the owner's explicit authorization. APM and SX are not mandatory dependencies of the
core, and the coding agent is not granted authority for production deployment.

## Alternatives

1. Leave independent runbooks and checks without a common barrier. This adds no
   mechanisms, but allows a release to be declared ready based on an incomplete set
   of fragmented evidence.
2. Automate release and remediation in production. This accelerates response, but
   violates the boundary of explicit owner approval and may turn an erroneous signal
   or abuse heuristic into an irreversible action.
3. Introduce evidence-gated readiness: automation only collects and validates safe
   evidence, while admission to production requires a complete set, a limited validity
   period, and explicit owner approval.

## Decision

Alternative 3 is accepted.

`SPEC-032` owns the Phase 10 readiness release process. It links, but does not
redefine, the existing owners of facts: data governance remains in `SPEC-013`,
the lifecycle of complaints and staff decisions remains in `SPEC-016`, telemetry
remains in `SPEC-017`, and topology, deploy, backup, restore, and rollback remain
in `SPEC-024` and `ADR-0044`.

Before a production change, there must be a verifiable set of evidence for the exact
commit. It includes the production configuration validation result, safe release
identity, current retention and deletion policy, SLO/alert policy, verification of
abuse constraints, the result of backup/restore and rollback rehearsal, as well as
explicitly named exceptions and residual risks. The set contains only safe links,
IDs, digests, timestamps, and outcomes; secrets, tokens, private bytes, personal
data, and env values are not included.

Evidence collection and verification may be automated and repeatable, but do not
perform deployment, recovery, cleanup, lifecycle changes, or any other production
write. Admission is a separate explicit owner decision on a still-valid evidence set;
expiration, a change to the commit/config/policy, or incompleteness require a new set.

Abuse protection is applied at the server boundary and observed through limited safe
signals. Client code, the number of complaints, and a single heuristic signal are not
a source of authority for blocking, deletion, data disclosure, or automatic
punishment. Such decisions retain the existing explicit audited staff actions.

## Consequences

- `SPEC-032` is introduced with requirements and executable criteria for #187;
- future implementation will add versioned policy references and a safe readiness
  evidence artifact, without copying the data schema, secrets, or object bytes into it;
- validation configuration, observability, abuse limits, and recovery rehearsal
  receive separate deterministic tests and operator evidence;
- exact numerical SLO targets, retention periods, and limit budgets are not chosen
  from memory: before production launch, they become an approved versioned policy;
- runbooks remain the means of executing operations; the new specification requires
  evidence from them rather than replacing them with a hidden control plane;
- production deployment, cleanup, recovery, and rollback still require the owner's
  explicit authorization.

## Amendment 2026-08-29: Who Makes the Admission Decision

The final consequence and the paragraph “Admission is a separate explicit owner
decision” were superseded by `ADR-0118`. The record is preserved: it accurately
describes the decision at the time it was accepted, when the “Agent Authority”
section was still a list of reasons to stop.

What changed: `ADR-0115` removed protections from repository participants,
`ADR-0118` extended the same principle to agent authority, and `ADR-0109` made
rollout a consequence of a green `check`, rather than a separate button press.
The agent makes the admission decision within the owner's vision and states
that decision in the report.

What **did not** change and remains in force here: the evidence is bound to the
exact commit and its bindings; an incomplete, rejected, or expired set does not
release; evidence collection does not perform a production write; and the
operation itself still requires a plan, an exact digest, re-verification of
preconditions, and idempotency. This is a machine guarantee of effect, not human
permission.

## Reconsideration Conditions

The decision must be reconsidered if a confirmed need arises for a separate
control plane, automatic remediation with limited authority, or a mandatory
APM vendor. Any such transition must separately define authority, rollback,
audit, data retention, and a safe failure mode.
