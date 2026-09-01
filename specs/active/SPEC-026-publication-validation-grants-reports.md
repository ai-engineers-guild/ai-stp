---
description: "SPEC-026: Server-side publication, validation jobs, grants, reports, and staff audit."
last_verified: "2026-08-25"
---

# SPEC-026: Server-side publication, validation jobs, grants, reports, and staff audit

## Purpose

The authenticated platform accepts a publication plan for an exact version,
runs server-side checks and idempotent worker jobs, grants rights to a major
line through an invitation, accepts private reports, and records staff actions
in an append-only audit. This slice implements the server side of `SPEC-007`,
`SPEC-002` (rights), and `SPEC-016`, and extends `SPEC-018`, without moving CLI
build, installation, or setup-editor logic into the API.

## Scope

Included are authenticated `/v1` routes for publication planning and
confirmation, invitations and rights, report cases, and staff moderation /
`author_verified`; durable PostgreSQL tables for publication plans, validation
snapshots, evidence bindings, `AccessGrant`, `GrantInvitation`, and
`ReportCase`; additive Alembic migrations in the shared tree under `SPEC-020`;
the closed job types `validate`, `publish`, `reevaluate_eligibility`, and
`deliver_invitation` with idempotent handlers; an invitation-delivery port
through Resend; a staff allowlist; redacted audit events; contract models,
fixtures, OpenAPI, and tests.

Excluded are CLI commands for publication, reports, and rights (P8-C2); web
screens for owned objects, rights, and administration (phase 9 / `#183`);
private revision sync (already `SPEC-025`); the local registry, setup compiler,
and provider writes to the target; full RBAC, organizations, payments, and
recipient-free link access; automatic blocking based on report count; remote
disabling of installed targets; and an external message broker or workflow
engine.

Wire-contract fields belong to `packages/contracts` and generated OpenAPI
(`SPEC-010`, `SPEC-015`). The required-check matrix is owned by
`docs/contracts/validation-policy.md`. Report contents are owned by
`docs/contracts/report-case.md`. Grant targets are owned by
`docs/contracts/access-grants-and-forks.md`. The mutating-operation state
machine is owned by `docs/contracts/operation.md`. The architectural decision
for this slice is `ADR-0067`. The author-attestation payload definition is
owned by `ADR-0092`. Artifact-byte binding is owned by `ADR-0093`.

## Terms

- `PublicationPlan` — an immutable server-side publication plan with
  `plan_hash`, expiry, digest, policy version, and a list of effects; a special
  case of Operation from `operation.md`.
- `ValidationSnapshot` — a durable validation result for an exact digest and
  policy version; it is not rewritten when policy is tightened.
- `EvidenceBinding` — an accepted source of evidence for one required check,
  with an expiry.
- `AccessGrant` / `GrantInvitation` — as defined by `SPEC-002` and `ADR-0020` /
  `ADR-0030`.
- `ReportCase` — as defined by `SPEC-016` and `ADR-0031`.
- `PlatformStaff` — an account in a closed configuration allowlist, without a
  full role model.

## Requirements

### Publication and validation jobs

- `REQ-2601`: Creating a `PublicationPlan` requires an active device for the
  current session, ownership of the object (or staff with audit), the exact
  authenticated account as passport owner, and a non-empty published public
  profile with publisher listing enabled. It also requires the exact
  content digest, an `X.Y` version, complete passport fields from `SPEC-007`
  REQ-706, a policy version, and an idempotency key. The response returns the
  plan id, `plan_hash`, `expires_at`, and effects.
- `REQ-2602`: Confirmation accepts only the `plan_hash` of a valid, unexpired
  plan and an explicit consent flag. An expired, `stale` (digest/policy/evidence
  changed), or already completed plan produces a typed error; repeating the same
  idempotency key returns the original operation without a second job.
- `REQ-2603`: After confirm, the server transitions the plan to `validating`,
  enqueues a `validate` job, and writes audit in one transaction. The server runs
  required checks that do not need credentials; a device report does not replace
  them (`SPEC-007` REQ-719).
- `REQ-2604`: The `validate` job creates a `ValidationSnapshot` and
  `EvidenceBinding` for every required matrix check. Required `failed` /
  `degraded` / `not_run` / `expired` results block publish; `warning` does not
  block it but does not grant `component_verified`.
- `REQ-2605`: Author attestation is accepted only as `author_attested` for
  credential-dependent checks. The sole payload definition is the closed
  `ai_stp_assurance.AuthorAttestation` record; wire `/v1` carries that same
  record, not a reduced projection or a second document reconstructed by the
  server. The server verifies the Ed25519 signature by the registered active
  device key over `attestation_digest` in the `ai-stp:attestation:v1` domain and
  verifies every coordinate against the publication plan. A revoked or foreign
  device, a changed coordinate, a malformed signature string, and secret fields
  are rejected (`SPEC-007` REQ-724, `ADR-0092`).
- `REQ-2606`: The `publish` job runs only after a snapshot in which all required
  checks have current accepted `passed` evidence. It atomically records immutable
  version metadata, the location of public bytes when needed, the catalog
  projection, `component_verified`, and lifecycle `published` / `active`.
  Republishing different bytes under the same `X.Y` is rejected (`SPEC-007`
  REQ-712). A new `X.Y` with artifact bytes already published for another
  version is allowed: `object_location` points to the same content-addressed key
  (`SPEC-020` REQ-2004).
- `REQ-2607`: When evidence expires or policy is tightened, the
  `reevaluate_eligibility` job removes `component_verified`, excludes the object
  from `authoritative`, and blocks new installations and updates without
  rewriting historical snapshots or installed targets (`SPEC-007`
  REQ-721/726, `ADR-0032`).
- `REQ-2608`: The first-party experimental seed path remains separate and does
  not mark objects as having passed the full publication barrier.
- `REQ-2628`: The complete `ai_stp_contracts.first_party` launch corpus is
  published only through the shared authenticated publication pipeline: an
  exact plan, durable artifact binding, confirmation of the exact hash,
  server-side validation, and a publication job. Components finish publication
  before dependent setups; retries resume saved coordinates and do not create a
  direct catalog write. First-party provenance changes neither validation
  policy, required evidence, `component_verified`, nor trust line. The operator
  batch `apps/cli/tools/first_party_launch_publication.py` only resumes this
  sequence.

### Rights and invitations

- `REQ-2609`: The owner creates a `GrantInvitation` for a normalized email
  address and `(stable_id, major)` pair, with an expiry and idempotency key. The
  response body and timing class are indistinguishable for known and unknown
  addresses (`SPEC-002` REQ-209).
- `REQ-2610`: An invitation is not a right. It is converted to an `AccessGrant`
  only when an account signs in with the same verified provider address; an
  unverified string match is rejected (`SPEC-002` REQ-210/211).
- `REQ-2611`: A grant permits reading, installing, and forking the `X.*` major
  line; writing to the original and re-granting are prohibited (`SPEC-002`
  REQ-216/217).
- `REQ-2612`: Invitation revocation and grant revocation are separate and apply
  prospectively; bytes already obtained are not deleted, and the owner is
  informed of this (`SPEC-002` REQ-212/218).
- `REQ-2613`: The `deliver_invitation` job sends email through the Resend port;
  transport failure is retried until dead-letter; the invitation token does not
  enter logs, metrics, or the audit payload (`SPEC-010` REQ-1009).
- `REQ-2625`: The owner may create a direct grant for an explicitly selected
  `github_username`. The username is lower-cased without `@`, checked against
  GitHub syntax, and resolved only through a linked active GitHub identity. An
  unknown or inaccessible username produces one `not found`; the selected type
  and normalized value are stored beside the grant and returned to the owner and
  recipient in the rights list.
- `REQ-2626`: The owner may create a direct grant for an explicitly selected
  `user_id`. The value must be a canonical account ID, is not case-folded, and
  is not heuristically recognized as a username. An unknown or inaccessible ID
  produces one `not found`; the grant stores a stable `grantee_account_id`,
  participates in the shared read and revocation matrix, and preserves the
  selected identifier type.

### Reports and moderation

- `REQ-2614`: Creating a report builds one `ReportCase` through the shared
  scenario; the payload is limited by `report-case.md`; extra fields are
  rejected before any write (`SPEC-016` REQ-1601/1602).
- `REQ-2615`: Optional diagnostics require a confirmed preview and are
  size-limited; a rate limit and idempotency key apply; duplicates are grouped
  (`SPEC-016` REQ-1603/1606).
- `REQ-2616`: Case states follow `report-case.md`. The author receives a
  redacted notification only after triage. A vulnerability label transitions
  the case to `security_escalated` without a public issue (`SPEC-016`
  REQ-1604/1605).
- `REQ-2617`: The number of reports never changes version lifecycle. Hiding,
  blocking, and restoration are explicit staff actions with a reason and an
  `AuditEvent` (`SPEC-016` REQ-1607, `SPEC-007` REQ-722).
- `REQ-2618`: A reporter sees only their own cases; the reporter's identity is
  hidden from the object author (`SPEC-016` REQ-1608).

### Staff, audit, and queue integrity

- `REQ-2619`: Granting and revoking `author_verified` is staff-only, manual,
  and audited with actor, subject, reason, and time; it is not derived
  automatically (`SPEC-007` REQ-715/716/717).
- `REQ-2620`: Staff authority comes from a closed allowlist of account
  identifiers in configuration. Outside the allowlist, access is permanently
  rejected without disclosing resource existence beyond the ordinary `404` /
  `403` policy.
- `REQ-2621`: Successful publication acceptance, grant changes, staff lifecycle
  actions, and report triage write append-only audit with a redacted payload
  (without tokens, invitation secrets, raw signatures, document bodies, or
  email contents).
- `REQ-2622`: A domain write and enqueue of a `validate` / `publish` /
  `reevaluate_eligibility` / `deliver_invitation` job occur in one PostgreSQL
  transaction; repeating an idempotency key does not create a second job
  (`SPEC-018` REQ-1805, `SPEC-010` REQ-1006).
- `REQ-2623`: Handlers are idempotent under at-least-once delivery. A transient
  failure receives bounded backoff; exhausting attempts produces `dead_letter`
  with a safe last_error and no automatic retry (`SPEC-018`
  REQ-1806/1807/1811).
- `REQ-2624`: The authority matrix covers owner, grantee, outsider, reporter,
  and staff for every route class; knowing an account id is not authority
  (`SPEC-010` REQ-1003).
- `REQ-2627`: Before confirm, the author binds verified artifact bytes to the
  plan through one authenticated plan-scoped upload. The server compares digest
  and size with the plan, rejects root escapes, links, device/special files, and
  size excess, writes the bytes immutably to object storage, and rejects confirm
  until the bytes are durable. Public version reads return exactly the accepted
  bytes and digest. A different body under the same `X.Y` is rejected
  (`SPEC-007` REQ-701/712, `SPEC-020` REQ-2005, `ADR-0093`).

## States and errors

Plan/operation states align with `operation.md` and the publication lifecycle
from `SPEC-007` (`draft`, `ready`, `validating`, `publish_planned`, `published`,
`deprecated`, `blocked`, `hidden` as applicable). Job states belong to
`SPEC-018`. Invitation states are `pending`, `accepted`, `expired`, and
`revoked`. Report case states are defined by `report-case.md`.

Typed errors distinguish validation, authn, authz, an idempotency conflict with
a different body, a stale plan, expired evidence, rate limiting, an unknown
policy object kind, and dependency unavailability. A revoked device is rejected
before a durable write on device-bound publication and attestation paths.

## Security and privacy

The server does not store author credentials: credential-dependent evidence is
author-attested only. Object-store keys are not authority; private bytes require
an owner/grant check on every serving route. Invitation tokens and OAuth secrets
do not enter audit/log/trace. Staff reads of private objects require a reason
when policy specifies one and always write audit. Report diagnostics are
redacted; home paths are shortened to relative paths.

## Compatibility and migration

Additive Alembic migrations follow the current head (after
`0006_sync_revision_ledger` or later). New API fields are initially optional
within the major wire version. The closed `JobType` registry in this slice is
extended only by the four names above. Older clients without
publish/grant/report routes remain valid. A rollback must read rows of the new
version during the compatibility window (`SPEC-010`).

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-2601` | A contract/API test creates a plan with the required fields and rejects another owner, a missing public publisher profile, or an incomplete passport, repository, license, or tags. |
| `REQ-2602` | Confirm with an invalid hash, an expired plan, and a repeated idempotency key. |
| `REQ-2603` | Fault injection before commit leaves neither `validating` nor a `validate` job. |
| `REQ-2604` | Fixtures for required `failed`, `degraded`, `not_run`, `expired`, and `warning` results. |
| `REQ-2605` | An attestation with a bad signature, a string of sixteen `s` characters, a revoked device, a shifted digest, or secret fields is rejected; an accepted record is verified with the device key over the canonical digest. |
| `REQ-2606` | Successful publish writes one version; another digest under the same `X.Y` is rejected; a new `X.Y` with the same artifact digest gets its own `object_location` row pointing to the same key; the catalog projection is visible. |
| `REQ-2607` | Expiry and policy tightening remove `component_verified` and block new installations without rewriting bytes. |
| `REQ-2608` | A seeded experimental object has no markers of the full publication barrier. |
| `REQ-2628` | A process test carries the complete `ai_stp_contracts.first_party` corpus through plan/bind/confirm/validate/publish, components before setups, repeats the run without a second effect, and proves the absence of seed/direct-write and first-party exceptions. |
| `REQ-2609` | A test verifies indistinguishable create-invitation responses. |
| `REQ-2610` | Accept with a foreign or unverified email is rejected; the happy path creates one grant. |
| `REQ-2611` | Matrix: the grantee can read, writing to the original and re-granting are prohibited, and major+1 is prohibited without a new grant. |
| `REQ-2612` | Revoking an invite and a grant are independent; the response states that local bytes are not deleted. |
| `REQ-2625` | API/web tests cover GitHub username normalization, unknown/invalid values, listing, and revocation. |
| `REQ-2626` | API/web tests cover create/list/authz/revoke by user ID and safe ID errors. |
| `REQ-2613` | `deliver_invitation` enters retry and then dead-letter; the token is absent from logs/audit. |
| `REQ-2614` | Prohibited report fields are rejected; there is one shared scenario entrypoint. |
| `REQ-2615` | Preview is required; rate limiting applies; idempotent create returns the same case. |
| `REQ-2616` | The lifecycle traverses its states; `security_escalated` is hidden from ordinary lists. |
| `REQ-2617` | N reports do not change the version; a staff block changes state and writes audit. |
| `REQ-2618` | The author cannot see the reporter's identity; an outsider cannot read another user's cases. |
| `REQ-2619` | Non-staff cannot grant `author_verified`; staff issue/revoke is audited. |
| `REQ-2620` | An account outside the allowlist cannot invoke staff routes. |
| `REQ-2621` | Audit redaction tests cover tokens, signatures, and documents. |
| `REQ-2622` | Transactional enqueue and a duplicate idempotency key. |
| `REQ-2623` | Double handler delivery has no second effect; dead-letter contains a safe error. |
| `REQ-2624` | Complete authz matrix by route class. |
| `REQ-2627` | A process or bind-layer test covers the plan, upload of real bytes, confirm, and anonymous reading matching the digest; a second body under the same `X.Y` and a dangerous archive are rejected. |
