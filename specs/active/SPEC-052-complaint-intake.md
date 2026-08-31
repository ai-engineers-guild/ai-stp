---
description: "SPEC-052: Public intake of complaints about an author, catalog object, or arbitrary target."
last_verified: "2026-08-22"
---

# SPEC-052: Public complaint intake

## Purpose

Accept a complaint about an author, component, setup, or arbitrary target without requiring an email client or a private `ReportCase`. Store who submitted it, whom/what it concerns, the subject, text, reply email, and account id if the submitter is signed in.

## Scope

Staff triage, the report case state machine, and the CLI `report` command are out of scope. The exact field contract belongs to `docs/contracts/complaint-intake.md`. The private authenticated case remains defined in `docs/contracts/report-case.md`.

## Terms

- **Complaint** — an intake record, not a report case.
- **Submitter** — either a signed-in account or an anonymous user with a reply email.

## Requirements

- `REQ-5201`: `POST /v1/complaints` accepts a complaint without requiring a session and stores the listed fields.
- `REQ-5202`: A signed-in caller is recorded as `submitter_account_id`; without a session, the field is empty.
- `REQ-5203`: The form does not depend on a configured mailto address and is not blocked by an email warning.
- `REQ-5204`: Limits are read from configuration: one submission per submitter per window and no more than the configured number per minute against a single component target and a single user target.
- `REQ-5205`: Exceeding a limit returns `AI_STP_RATE_LIMITED`. Tests read the same settings as the handler.

## States and errors

Success is `201` with `complaint_id` and without echoing the text. Validation errors use `AI_STP_VALIDATION_ERROR`. Rate limiting uses `AI_STP_RATE_LIMITED`.

## Security and privacy

The text is scanned for prohibited secret markers. For rate limiting, an anonymous submitter is identified only by the normalized reply email, not by the network address.

## Compatibility and migration

An additive table and route. Rollback removes the intake endpoint; the private `POST /v1/reports` remains unchanged.

## Acceptance criteria

| Requirement | Executable evidence |
|---|---|
| `REQ-5201` | An API test creates author/component/other complaints and reads the stored fields. |
| `REQ-5202` | The same test distinguishes an anonymous submitter from a signed-in submitter. |
| `REQ-5203` | The web form submits to the API and does not display a warning about unconfigured email. |
| `REQ-5204` | The test obtains limits from the handler's settings object. |
| `REQ-5205` | An excess request receives `AI_STP_RATE_LIMITED`. |
