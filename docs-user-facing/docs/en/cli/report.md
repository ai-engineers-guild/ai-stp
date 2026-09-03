---
title: "Reports"
description: "Preview, confirm, and list closed report cases."
---

# Reports

A report opens a closed moderation case about one exact object version. It
is not a public discussion, not a GitHub issue, and not a passport note.
The payload is bounded and previewed before it is sent.

Preview writes nothing to the server. Confirm submits one exact preview
after `--confirm`. List shows this account's closed cases. The website can
open the same kind of case; the CLI is the path that binds an exact
content digest you already hold.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp report preview` | `plan` | `none` | prepare and show the exact bounded payload without sending it |
| `ai-stp report confirm` | `apply` | `explicit_flag` | submit one exact durable preview after explicit confirmation |
| `ai-stp report list` | `read` | `none` | list the current account's closed report cases |

`--json` is global. Always pass it.

## Preview

```bash
ai-stp report preview \
  --kind component \
  --id <stable_id> \
  --version 1.0 \
  --content-digest sha256:... \
  --idempotency-key <key> \
  --json
```

`--kind` is `component` or `setup`. `--id`, `--version`, `--content-digest`,
and `--idempotency-key` are required.

Optional context, when you have it:

```bash
ai-stp report preview \
  --kind setup \
  --id <stable_id> \
  --version 1.0 \
  --content-digest sha256:... \
  --harness-id codex \
  --harness-version 0.140.1 \
  --provider-version 1.2.3 \
  --operation-id <operation_id> \
  --error-code AI_STP_PRECONDITION_FAILED \
  --validation-snapshot-id <snapshot_id> \
  --diagnostics-file ./diagnostics.txt \
  --vulnerability \
  --idempotency-key <key> \
  --json
```

`--harness-id`, `--harness-version`, `--provider-version`, and
`--operation-id` are optional. `--error-code` is a related registered error
code. `--validation-snapshot-id` is repeatable. `--diagnostics-file` is a
bounded pre-reviewed UTF-8 file. `--vulnerability` marks a possible
security vulnerability.

Do not put secrets, tokens, `.env` bodies, or personal data in the
diagnostics file. The preview shows exactly what would be sent.

Success fields: `plan_id`, `plan_digest`, `report`, `submitted`. `report`
echoes `object_kind`, `stable_id`, `version`, `content_digest`,
`idempotency_key`, and the optional fields you set. `submitted` is false.

## Confirm

```bash
ai-stp report confirm \
  --plan-id <plan_id> \
  --plan-digest sha256:... \
  --confirm \
  --json
```

`--plan-id`, `--plan-digest`, and `--confirm` are required. The digest is
the one `preview` returned. A changed payload is a new preview.

Success fields: `case_id`, `object_kind`, `stable_id`, `version`, `state`,
`vulnerability`, `created_at`. The case is closed: it is not a public
thread.

## List

```bash
ai-stp report list --json
```

Success fields: `items`, each with `case_id`, `object_kind`, `stable_id`,
`version`, `state`, `vulnerability`, `created_at`.

## Happy path

```text
registry version --kind component --id <id> --version 1.0
→ copy content digest from the verified passport
→ report preview --kind component --id <id> --version 1.0 --content-digest sha256:... --idempotency-key <key>
→ read the payload
→ report confirm --plan-id <plan_id> --plan-digest sha256:... --confirm
→ report list
```

If the preview is wrong, do not confirm. Build a new preview with a new
idempotency key only when the intent is actually different.

## Named success fields

| Command | Fields to read |
| --- | --- |
| `preview` | `plan_id`, `plan_digest`, `report`, `submitted` |
| `confirm` | `case_id`, `state`, `vulnerability`, `created_at` |
| `list` | `items` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | no signed-in account | `auth login` |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` was omitted | pass `--confirm` after reading the preview |
| `AI_STP_VALIDATION_ERROR` | `--kind`, `--id`, `--version`, `--content-digest`, or `--idempotency-key` missing | correct the request |
| `AI_STP_PLAN_STALE` | `--plan-digest` no longer matches the stored preview | preview again |
| `AI_STP_NOT_FOUND` | the plan id is unknown | `report preview` first |
| `AI_STP_CONFLICT` | the idempotency key already names a different payload | new key for a new intent |
| `AI_STP_PRECONDITION_FAILED` | the diagnostics file is not bounded UTF-8, or the digest is not that version | shrink the file; copy the digest from the version passport |
| putting a token in diagnostics | reports must not carry secrets | redact; preview again |

A vulnerability mark does not publish a CVE and does not take the object
down by itself. It flags the closed case. Staff triage is on the server.

## Related links

- [Registry](registry.md)
- [Owner objects](owner.md)
- [Publication](publication.md)
- [Web reports](../web/reports.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups report commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
