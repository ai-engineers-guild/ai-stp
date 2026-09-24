---
description: "Closed heartbeat payload the CLI sends for its corporate installation, and the command behavior around it."
last_verified: "2026-09-24"
---

# CLI installation heartbeat

The requirements owner is `SPEC-087` (`REQ-8701`–`REQ-8713`); decisions are
`ADR-0204`, `ADR-0208`, and `ADR-0209`. This document defines the machine boundary: the field list, the
commands, and the sending rules. This channel is unrelated to the anonymous
consented ping (`cli-telemetry.md`, ADR-0112), which is untouched.

All heartbeat egress is authenticated `PUT`/`GET` under
`/v1/corporate/organizations/{organization_id}/telemetry/` using the held
device-bound session. The CLI reads the organization heartbeat policy before
opt-in and before an automatic send. There is no body outside the closed request model, and no
field outside the table may be added without changing this document and
`SPEC-087`.

## Request fields

| Field | Example | Source |
| --- | --- | --- |
| `account_id` | `account_01J…` | held session |
| `device_id` | `device_01J…` | held session |
| `cli_version` | `1.4.2` | installed distribution version |
| `capabilities` | `["cli.heartbeat", "harness.claude-code@1.2.3", "provider.claude-code@2.1.0"]` | token vocabulary below |
| `last_sync_at` | `2026-09-22T11:00:00.000Z` | last successful local sync cursor or null |
| `health_state` | `active`, `partial`, `failing`, `disabled` | local facts by default; explicit override accepted |
| `checked_at` | `2026-09-22T12:00:00.000Z` | client clock at build time |

## Capability tokens

Each capability is `name` or `name@version` over the alphabet
`[a-z0-9._-]` for names and `[A-Za-z0-9.+_-]` for versions. The alphabet
excludes whitespace and path separators by construction, so a capability can
never carry a path, an environment value, or a secret. The CLI emits
`cli.heartbeat`, only locally detected harnesses, and a `provider.<harness>@<version>`
token only when the resolved provider executable matches its local release
manifest digest. Provider code is never run to build a heartbeat. Supported but
absent harnesses are not reported.

## Commands

- `heartbeat send --organization <id> [--state active|partial|failing|disabled]
  [--last-sync-at <timestamp>]` — write one beat. Without `--state`, the CLI
  derives state from installed harnesses and provider evidence. Replays and
  delayed beats coalesce server-side; an offline explicit send returns the
  typed transport failure.
- `heartbeat enable --organization <id>` — after device-bound authentication,
  confirm that organization policy permits reporting and opt this local CLI
  installation in. The subscription is tied to this account and device. A
  per-user OS wakeup is registered before opt-in is saved; a registration
  error refuses autonomous enrollment.
- `heartbeat disable --organization <id>` — remove local opt-in without a
  network request, then remove its OS wakeup.
- `heartbeat tick --organization <id>` — one offline-safe due check for the
  named local subscription. It sends only when the organization policy and
  SQLite retry schedule allow it; it cannot create opt-in.
- `heartbeat local-status --organization <id>` — offline view of opt-in,
  scheduler registration, and the next/last attempt timestamps.
- `heartbeat status --organization <id>` — this installation's evaluated
  health (`unknown` before the first beat).
- `heartbeat installations --organization <id> [--health <state>]` — the
  health list visible to the caller's role.

After a successful ordinary CLI command, the CLI attempts at most one due
subscription, ordered by oldest due time. Authentication and heartbeat
commands do not trigger automatic sending. The snapshot is rebuilt on every
attempt; no report body or credential is queued locally. Network work is
bounded to one policy lookup and one write attempt, each with a two-second
timeout. Failures do not change the command result and schedule an
organization-bounded exponential retry. Successful sends wait for the
organization interval. An hourly per-user OS wakeup invokes the same sender
while the user session and host scheduler are available. Windows uses Task
Scheduler, macOS uses LaunchAgent, Linux uses a user systemd timer, and WSL
uses a Windows task to launch the named distribution. No Python daemon stays
resident. The installed Python path and effective XDG config/data directories
are captured in the local task; repeat `enable`
after moving or reinstalling the CLI. A sleeping, powered-off, or logged-out
host may become `stale`. Local `disable` does not report `disabled` to the API;
the last row eventually projects as `stale`.

## Never sent

Prompts, model inputs or outputs, command arguments, MCP payloads, repository
or source contents, local paths, environment values, credentials, and secrets.
A heartbeat is not a component invocation and produces no usage event.
