---
description: "SPEC-016: Object reports and moderation."
last_verified: "2026-08-04"
---

# SPEC-016: Reports and moderation

## Purpose

A user reports a broken or malicious published object to the platform from the web or CLI without disclosing their private data, while moderators review cases and make explicit, auditable decisions about version lifecycles.

## Scope

Includes creating a private case from the web and CLI, the mechanically defined report contents, preview and consent, triage, author notification, vulnerability escalation, duplicate grouping, rate limits, and auditable moderator actions. Public issues created from reports, ratings, public discussions, and automatic blocking based on the number of reports are out of scope.

The permitted report contents and list of states are owned by `docs/contracts/report-case.md` and are not repeated here.

## Terms

- `ReportCase` — an internal private report case concerning an exact object version.
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
