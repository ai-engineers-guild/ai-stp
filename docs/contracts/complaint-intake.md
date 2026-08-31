---
description: "Public complaint intake: fields, distinction from a private report case, and configurable limits."
last_verified: "2026-08-22"
---

# Complaint intake

This differs from the private `report-case.md`: it is not an authenticated case
with a version digest and state machine. A web form accepts a complaint about an
author, catalog object, or arbitrary target and stores it as submitted.

## Record fields

| Field | Meaning |
|---|---|
| `complaint_id` | Typed `complaint_<ULID>`. |
| `target_kind` | `author` \| `component` \| `setup` \| `other`. |
| `target` | Who or what the complaint concerns: account ID, `stable_id@version`, or a free-form label. |
| `sender_name` | Sender. |
| `reply_email` | Reply address. |
| `subject` | Subject. |
| `message` | Message body. |
| `submitter_account_id` | Signed-in account ID, or absent for an anonymous submitter. |
| `created_at` | Intake time. |

Secrets, tokens, keys, and `.env` contents are prohibited in the subject, body,
and target.

Wire models belong to `packages/contracts`; the route belongs to generated
OpenAPI. This document owns field meaning and the distinction from a report case.

## Limits

Values come from process configuration with the `AI_STP_COMPLAINT_` prefix, not
from handler literals:

- per submitter: `SUBMITTER_LIMIT` per `SUBMITTER_WINDOW_SECONDS` (default: 1 per
  300 s). The key is the signed-in `account_id`, or `email:` plus normalized
  `reply_email`;
- per target: `TARGET_LIMIT` per `TARGET_WINDOW_SECONDS` (default: 50 per 60 s),
  separately for each `(target_kind, target)` pair.

Exceeding a limit responds with `AI_STP_RATE_LIMITED`. The staff triage UI is
outside this contract.
