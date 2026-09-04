---
description: "SPEC-016: Private requests and moderation."
last_verified: "2026-09-04"
---

# SPEC-016: Requests and moderation

## Purpose

A user reports a broken or malicious published object to the platform from the web or CLI without disclosing their private data, while moderators review cases and make explicit, auditable decisions about version lifecycles.

## Scope

Includes creating a private case from the web and CLI, the mechanically defined report contents, preview and consent, triage, author notification, vulnerability escalation, duplicate grouping, rate limits, and auditable moderator actions. Public issues created from reports, ratings, public discussions, and automatic blocking based on the number of reports are out of scope.

The permitted report contents and list of states are owned by `docs/contracts/report-case.md` and are not repeated here.

## Terms

- `ReportCase` — an internal private case routed by a closed stable topic code.
- `triage` — initial classification of a case by a platform moderator.
- `sanitized notification` — a message to the author without the reporter's identity or environment.

## Requirements

- `REQ-1601`: The report action on the web and the report command in the CLI create one private `ReportCase` through a shared application flow; a public GitHub issue is not created automatically.
- `REQ-1602`: The report payload is restricted to the allowlist in `docs/contracts/report-case.md`; source code, prompts, `.env` contents, secret values, private bytes, and full home paths are not sent automatically.
- `REQ-1603`: Optional diagnostics are size-limited, sanitized, and sent only after the reporter explicitly previews and consents to them; sending without a preview is impossible.
- `REQ-1604`: A case progresses through the closed list of states in `docs/contracts/report-case.md`; the author receives only a sanitized notification and only after triage.
- `REQ-1605`: A case showing signs of a vulnerability is escalated to the private process in `SECURITY.md` without publishing details.
- `REQ-1606`: Duplicate reports for one version are grouped; submission requires an account, is rate-limited, and is idempotent by key.
- `REQ-1607`: The number of reports alone never hides or blocks an object; hiding, blocking, and restoration are performed only by an explicit moderator action with an audit event.
- `REQ-1608`: A reporter can see the state of their own cases; other cases and the reporter's identity are disclosed neither to the author nor to other users.
- `REQ-1609`: Authenticated users and the CLI submit service and country proposals through `POST /v1/requests`; the existing `report_case` table, lifecycle, rate limit, idempotency, and staff worklist are reused and cases are routed by `topic`.
- `REQ-1610`: A service proposal contains its name, shallow public HTTPS URL,
  Russian and English descriptions, source URL, and zero or more existing ISO
  country codes. A country proposal contains an uppercase ISO alpha-2 code and
  Russian and English names. Public names and descriptions are normalized
  UTF-8 text containing Unicode letters/digits, whitespace, and basic ASCII
  punctuation only; invisible/typographic characters, markup, unsafe URIs,
  profanity, sexual content/services, threats/violence, extremism, and
  military-action markers are rejected.
  The denylist matches complete words or explicit phrases at word boundaries;
  it does not match roots or suffixes inside otherwise valid words.
- `REQ-1611`: No HTTP operation turns a proposal into catalog metadata. An operator applies an accepted proposal manually at the database/server boundary.
- `REQ-1612`: Applying a catalog proposal by case id is one idempotent database transaction: it writes RU/EN presentation rows, replaces requested country relationships, queues RU/EN SEO builds, and resolves the case. A service with no countries remains valid.
- `REQ-1613`: The shared request flow accepts `component_complaint`,
  `author_complaint`, `ownership_transfer`, `verification_request`, and `other`
  in addition to existing proposal topics. `other` requires a bounded custom
  subject; component, author, recipient-account, reason, and evidence fields are
  required only for topics that use them.
- `REQ-1614`: Any authenticated account, including AI STP Official, may submit
  an ownership-transfer or verification request. Submission does not require or
  modify `author_verified`, component ownership, source state, or catalog state.
- `REQ-1615`: The web report form presents localized RU and EN labels and
  validation for every topic, preselects a component or author target when
  opened from that page, and stores stable English topic codes. User-authored
  subject, message, and evidence text is retained in the submitted locale and
  is not machine-translated.
- `REQ-1616`: No HTTP moderator operation transfers ownership or grants/revokes
  `author_verified`. Staff may read and triage requests; an operator applies an
  approved transfer or verification decision through one idempotent audited
  database-bound operation that references the case.

## States and errors

Case states are owned by `docs/contracts/report-case.md`. Errors distinguish an unknown object or version, rate-limit excess, a duplicate idempotency key, oversized diagnostics, and server unavailability; server unavailability returns a typed reason and does not lose the locally prepared report.

## Security and privacy

A report is not a data-collection channel: the allowlist is closed, and everything beyond it is rejected before sending. The reporter's identity is available only to moderators. Moderation logs contain neither secrets nor private bytes. Moderator actions use least privilege and create immutable audit events under `SPEC-002`.

## Compatibility and migration

The case schema is versioned; new optional fields are compatible within the major version. Changing the content allowlist requires a new schema version and a preview update. Historical cases retain their original schema and are not rewritten.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1601` | A contract check proves one flow for the web and CLI and the absence of an integration that creates a public issue from a report. |
| `REQ-1602` | Fixtures containing source code, secrets, private bytes, and home paths are rejected before sending. |
| `REQ-1603` | A report with diagnostics but without a confirmed preview is rejected, and exceeding the size limit produces a typed error. |
| `REQ-1604` | A lifecycle fixture traverses all states, and the author notification contains neither the reporter's identity nor environment. |
| `REQ-1605` | A case marked as a vulnerability transitions to `security_escalated` and does not appear in ordinary lists. |
| `REQ-1606` | Repeating a key returns the same case, duplicates are grouped, and exceeding the rate limit is rejected. |
| `REQ-1607` | A fixture with many reports does not change the version state, while a moderator action changes it and creates an `AuditEvent`. |
| `REQ-1608` | The authorization matrix allows the reporter to access only their cases and hides the reporter's identity from the author. |
| `REQ-1609` | API and CLI tests submit all topics through `/v1/requests` and assert one `report_case` lifecycle and worklist. |
| `REQ-1610` | Contract tests reject incomplete topic payloads, unsafe public text across profanity, sexual content/services, threats/violence, extremism, and military-action markers, and accept a service with an empty country list and a localized country request. |
| `REQ-1611` | The served-surface contract proves that no external-product creation or proposal-application HTTP route exists. |
| `REQ-1612` | A PostgreSQL integration test applies a service request with no countries and observes two locale rows, two SEO jobs, a resolved case, and the public service read. |
| `REQ-1613` | Contract tests accept every topic, enforce topic-specific fields, and require a custom subject only for `other`. |
| `REQ-1614` | An unverified account and AI STP Official both submit ownership requests without changing verification, ownership, or source state. |
| `REQ-1615` | RU/EN browser tests exercise every label and target-aware form while API fixtures retain stable topic codes and original user text. |
| `REQ-1616` | The served-surface contract contains no ownership or verification decision route; database integration tests apply each referenced case once and audit the operator. |
