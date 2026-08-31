---
description: "Decision to materialize the server-side flow for publication, validation jobs, grants, reports, and staff audit on top of the existing PostgreSQL queue."
last_verified: "2026-08-08"
---

# ADR-0067: Server-Side Flow for Publication, Validation Jobs, Grants, Reports, and Staff Audit

Status: accepted.

## Context

The product rules have already been established:

- full publication and evidence sources — `ADR-0026`, `SPEC-007`,
  `docs/contracts/validation-policy.md`;
- install eligibility based on current evidence — `ADR-0032`;
- rights to a major line, forks, and derivative publication — `ADR-0030`,
  `ADR-0020`, `SPEC-002`;
- closed reports and moderation — `ADR-0031`, `SPEC-016`;
- queue and transactional enqueueing — `ADR-0038`, `SPEC-018`;
- vertical API slices — `ADR-0037`;
- synchronization of private revisions (`#179`) — `ADR-0045`, `SPEC-025`.

After Sprint 1 and `#179`, PostgreSQL, Alembic, the `job` table, `upload` /
`update` worker stubs, `catalog_metadata` with an experimental seed, OAuth,
sessions, devices, append-only `audit_event`, and an object store are in
place. There are no tables or APIs for `AccessGrant`, `GrantInvitation`,
`ReportCase`, `ValidationSnapshot`, publication plans, actual
validation/publish handlers, staff actions for `author_verified` / lifecycle,
or invitation delivery through Resend.

Issue `#181` (key `P8-06`) requires assembling this server-side flow so that:

- the exact plan, idempotency, evidence expiration, policy, rights, reports,
  audit, and authorization are covered by tests;
- retries and dead-letter handling have operational evidence;
- the CLI and web UI remain outside the slice boundaries (client commands —
  `P8-C2`, web own objects — phase 9).

External practices for transactional outbox, at-least-once delivery,
dead-letter handling, and idempotent consumers align with the already
accepted `ADR-0038`: the domain record and job enqueueing occur in the same
transaction; the handler must tolerate retries. A new broker dependency or
workflow engine (Temporal and similar products) is not justified for the MVP.

## Alternatives

1. A single monolithic "platform service" with publication, rights, and
   reports in a shared layer. Faster to start, but it violates `ADR-0037` and
   mixes authorization, lifecycle, and side effects.
2. Five independent services or brokers (publish, validate, grants, reports,
   email). Scalable, but introduces dual-write, a second operational system,
   and conflicts with `ADR-0009` / `ADR-0038`.
3. A single issue slice on top of the existing PostgreSQL: vertical API
   slices, extension of the closed `JobType`, durable domain tables, Resend
   as a delivery port, and a staff allowlist without full RBAC. The product
   SPECs are not rewritten.

## Decision

Alternative 3 is accepted.

### 1. One Implementation Slice, Five Domain Boundaries

`#181` materializes the server-side portion of the already accepted rules
without creating a parallel policy. Ownership of meaning remains as follows:

| Area | Owner of meaning | Server-side materialization in `#181` |
|---|---|---|
| validation and publication | `SPEC-007`, validation-policy | plan/confirm API, snapshots, jobs |
| rights and invitations | `SPEC-002`, access-grants-and-forks | tables, invite/accept/revoke API |
| reports and moderation | `SPEC-016`, report-case | report API, staff lifecycle |
| queue | `SPEC-018`, `ADR-0038` | new job types and handlers |
| audit | `SPEC-002`, `SPEC-010` | extended closed set of actions |

### 2. Vertical API Slices

The following slices are added to `apps/api` (directory names may match the
route):

- `publish` — publication plan, confirmation, status, and cancellation before
  an irreversible effect;
- `grants` — invitation, list, revocation of an invitation or right, and an
  accept hook at sign-in;
- `reports` — creation and listing of the actor's own cases, staff triage, and
  actions;
- `staff` (or moderation within reports/publish) — granting and revoking
  `author_verified`, and version states `blocked` / `hidden` / restore.

The web and CLI invoke one application scenario and one `/v1` route
(`SPEC-010` REQ-1011). DTOs are in `packages/contracts`; ORM is in
`ai_stp_platform.models`; domain invariants are in the slice.

### 3. Extension of the Closed Job Type Registry

The following are added to `upload` and `update` additively:

| JobType | Purpose |
|---|---|
| `validate` | server-side credential-free checks and binding author attestations to `ValidationSnapshot` |
| `publish` | after successful validation: immutable version, object location, catalog projection, `component_verified` |
| `reevaluate_eligibility` | expiration or policy tightening removes the badge and install eligibility without rewriting bytes |
| `deliver_invitation` | invitation email delivery through the Resend port |

Signing or writing an object to the store remains a step within `upload` /
`update` / `publish`, rather than a separate type (`SPEC-018`). A new type is
added only by changing the closed registry and its registry tests.

Job enqueueing uses a transactional outbox in the same transaction as the
domain record; delivery is at least once; handlers are idempotent by business
key (`plan_id`, `snapshot_id`, `invitation_id`, version digest). Exhausting
attempts transitions the job to `dead_letter` without automatic retry;
dead-letter stores a safe `last_error`.

### 4. Publication Plan as a Server-Side Operation

Publication is not reduced to a single POST. The server stores an immutable
`PublicationPlan` (a special case of `docs/contracts/operation.md`):

- actor, device, object identity, exact content digest, policy version,
  evidence references, effects, `expires_at`, `plan_hash`;
- confirm applies only to this hash;
- changing the digest, policy, or evidence makes the plan `stale` and requires
  a new plan;
- after confirm: `validating` → `validate` job → `publish_planned` /
  publishing → `publish` job → `published` or a typed rejection;
- repeating confirm or the idempotency key returns the same operation, not a
  second effect.

The experimental seed (`SPEC-021`) is not part of this flow: the seed remains
a first-party bypass explicitly labeled experimental and does not substitute
for the full publication barrier.

### 5. Rights: Invitation → Grant

`ADR-0020` / `ADR-0030` is implemented without weakening it:

- `GrantInvitation` and `AccessGrant` are separate tables;
- the create-invitation response is indistinguishable for known and unknown
  email addresses;
- acceptance is allowed only when the address verified by the provider
  matches;
- the target of the right is the major line `(stable_id, major)`;
- revocation applies prospectively; bytes already held by the recipient are
  not erased;
- the email token is not included in logs/audit payload; Resend is transport
  only (`SPEC-010` REQ-1009).

### 6. Reports and Staff

- one `ReportCase` scenario for web and CLI;
- closed payload according to `report-case.md`;
- rate limiting, idempotency key, and grouping;
- the number of reports does not change the version lifecycle;
- staff actions (`triage`, `block`, `hide`, `restore`, granting and revoking
  `author_verified`) require the platform-staff allowlist (account ID from
  configuration) and always write an `AuditEvent` with the rationale;
- full RBAC and organization roles are deferred.

### 7. Audit

The existing append-only `audit_event` is extended with a closed set of
`action` strings for publish/grant/report/staff. Payload sanitization inherits
the audit helper in `apps/api`; secrets, invitation tokens, raw attestation
signatures, and email bodies are not stored.

### 8. Deliberately Out of Scope

- CLI commands for publish/report/grant (`P8-C2`);
- web screens for own objects and rights (phase 9 / `#183`);
- automatic merging of the local registry and CRDT;
- remote disabling of installed targets (`ADR-0032`);
- payments, organization SSO, access by a link without an addressee;
- a Temporal / Celery / Redis broker;
- rewriting historical `ValidationSnapshot` bytes when the policy is
  tightened.

## Consequences

- `SPEC-026` is introduced with executable requirements for the server-side
  materialization of `#181`;
- `SPEC-018` extends the closed `JobType` registry;
- `SPEC-020` no longer excludes rights, reports, and publication plan tables
  from the future migration tree — they are authored by `#181` in the same
  Alembic tree;
- `packages/contracts` and OpenAPI receive additive routes and schemas before
  the handlers;
- worker handlers cease to be pure stubs for validation, publish, eligibility,
  and invite;
- operations receive queue depth, retry, and dead_letter metrics for the new
  types (`docs/operations/observability.md`);
- the product `SPEC-002`, `SPEC-007`, and `SPEC-016` are not duplicated:
  the implementation SPEC references them.

## Reconsideration Conditions

The decision is reconsidered if:

- the frequency and diversity of jobs exceed the capabilities of the
  PostgreSQL queue (reconsider `ADR-0038`);
- the staff allowlist proves insufficient and roles or organizations are
  required;
- Resend or the email transport requires a separate compliance flow;
- a measured need emerges for a multi-step saga orchestrator instead of a
  chain of idempotent jobs.
