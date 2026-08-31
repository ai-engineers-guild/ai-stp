---
description: "Private report case: allowed content, preview, states, and auditable moderator actions."
last_verified: "2026-08-13"
---

# Report case

The requirements owner is `SPEC-016`; the decision is `ADR-0031`. This document defines the machine boundary: what a report contains, which states a case passes through, and what a moderator may do.

The web report action and CLI report command create one internal private `ReportCase` through the shared application flow under `ADR-0018`. A public GitHub issue is not created automatically from a report.

## Allowed content

The CLI collects only mechanical fields:

| Field | Content |
|---|---|
| object | stable identifier, version, and exact hash |
| harness | harness identifier and version |
| provider | provider version |
| operation | operation identifier and stage, if the report concerns an operation failure |
| checks | check snapshot identifiers |
| error | typed error code |
| diagnostics | optional, size-bounded, and sanitized; only after explicit review and consent |

Source code, prompts, `.env` contents, secret and environment-variable values, private object bytes, and full home paths are never sent automatically in any field. Paths in diagnostics are reduced to relative paths. The reporter sees a full preview of the report bytes before submission; submission without consent after preview is impossible.

The CLI expresses this boundary through three commands. `report preview`
validates the closed wire model, rejects diagnostics containing absolute paths
or secret-bearing assignments, and stores the exact payload with its digest and
idempotency key. `report confirm` requires the exact `plan_id`, digest, and
`--confirm`; after a lost response, a retry uses the stored payload and the same
key. A successful response is stored locally, so a later retry creates no new
network effect. `report list` reads the reporter's cases from the server.

Optional diagnostics are read only from a bounded regular UTF-8 file without
following symlinks. All of its text is included in the `preview` result; there
is no separate path for sending bytes not shown to the user.

## States

```text
submitted → triaged → awaiting_author → resolved | dismissed
                    ↘ security_escalated
```

| State | Meaning |
|---|---|
| `submitted` | the case has been created and awaits triage |
| `triaged` | a moderator has classified the case |
| `awaiting_author` | a sanitized notification has been sent to the author; a response is pending |
| `security_escalated` | the case has been transferred to the private vulnerability process |
| `resolved` | the case has been closed with an outcome |
| `dismissed` | the case has been closed without action |

The object author is notified only after triage and only in sanitized form: the reporter's identity and environment are not disclosed.

## Grouping and limits

Repeated reports for one object and version may be grouped into one case. Submission requires an account, is rate-limited, and is idempotent by key. Report count never automatically hides or blocks an object.

## Moderator actions

Hiding, blocking, and restoring a version are explicit moderator actions; each creates an `AuditEvent` with the actor, rationale, and time. Version lifecycle changes are governed by `SPEC-005` and `SPEC-007`; a report case merely references the decision and is not the decision itself.
