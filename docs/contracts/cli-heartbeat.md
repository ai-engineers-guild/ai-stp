---
description: "Closed heartbeat payload the CLI sends for its corporate installation, and the command behavior around it."
last_verified: "2026-09-22"
---

# CLI installation heartbeat

The requirements owner is `SPEC-087` (`REQ-8701`–`REQ-8709`); the decision is
`ADR-0204`. This document defines the machine boundary: the field list, the
commands, and the sending rules. This channel is unrelated to the anonymous
consented ping (`cli-telemetry.md`, ADR-0112), which is untouched.

All heartbeat egress is authenticated `PUT`/`GET` under
`/v1/corporate/organizations/{organization_id}/telemetry/` using the held
device session. There is no body outside the closed request model, and no
field outside the table may be added without changing this document and
`SPEC-087`.

## Request fields

| Field | Example | Source |
| --- | --- | --- |
| `account_id` | `account_01J…` | held session |
| `device_id` | `device_01J…` | held session |
| `cli_version` | `1.4.2` | installed distribution version |
| `capabilities` | `["cli.heartbeat", "harness.claude-code"]` | token vocabulary below |
| `last_sync_at` | `2026-09-22T11:00:00.000Z` | caller or null |
| `health_state` | `active`, `failing`, `disabled` | caller report |
| `checked_at` | `2026-09-22T12:00:00.000Z` | client clock at build time |

## Capability tokens

Each capability is `name` or `name@version` over the alphabet
`[a-z0-9._-]` for names and `[A-Za-z0-9.+_-]` for versions. The alphabet
excludes whitespace and path separators by construction, so a capability can
never carry a path, an environment value, or a secret. The CLI emits
`cli.heartbeat` plus one `harness.<id>` token per supported harness.

## Commands

- `heartbeat send --organization <id> [--state active|failing|disabled]
  [--last-sync-at <timestamp>]` — write one beat. Replays and delayed beats
  coalesce server-side; an offline send fails with a typed transport failure
  and is retried by the caller's scheduler.
- `heartbeat status --organization <id>` — this installation's evaluated
  health (`unknown` before the first beat).
- `heartbeat installations --organization <id> [--health <state>]` — the
  health list visible to the caller's role.

## Never sent

Prompts, model inputs or outputs, command arguments, MCP payloads, repository
or source contents, local paths, environment values, credentials, and secrets.
A heartbeat is not a component invocation and produces no usage event.
