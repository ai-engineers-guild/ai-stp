---
description: "Opted-in installation heartbeats use per-user OS wakeups while the CLI retains due times and retries."
last_verified: "2026-09-25"
---

# ADR-0209: User-scheduled installation heartbeats

Status: accepted. Extends ADR-0208 for the case where the CLI is idle.

## Context

ADR-0208 sends due heartbeats after ordinary CLI commands. An idle installation
therefore becomes stale even when the machine is on and the user remains logged
in. A Python scheduler started inside a short-lived CLI process exits with that
process; an always-running Python daemon would require another lifecycle.

## Decision

`heartbeat enable` registers a per-user OS wakeup every 30 seconds for the
opted-in organization. The wakeup invokes `heartbeat tick --organization <id>` through
the installed Python interpreter and a small local launcher that restores the
enrolled XDG config/data directories and credential-store selection. The tick
calls the same SQLite due claim, organization policy lookup, fresh report
assembly, and bounded retry
path as ordinary CLI invocations. `heartbeat disable` removes local opt-in
before removing the wakeup, so a removal failure cannot cause another send.
The tick does not infer opt-in from the presence of an OS task.

Windows uses a Task Scheduler task with two staggered minute triggers under
the interactive user with missed-run catch-up; macOS uses a LaunchAgent with a
30-second interval and
`RunAtLoad`; Linux uses a user `systemd` timer with `Persistent=true`. WSL
registers a Windows task that starts the named distribution and user through
`wsl.exe`, because its own systemd timer does not keep an idle WSL instance
alive. No administrator privilege, new credential, or third-party runtime
dependency is required.

The wakeup frequency is independent of the organization's send interval. The
organization may choose a send interval as low as 60 seconds. Twice-per-minute
checks allow for CLI startup and report assembly time without turning a missed
due check into a two-minute send gap. The CLI reports the local subscription,
scheduler registration, and recent
attempt timestamps through `heartbeat local-status`. A failed scheduler
registration prevents `enable` from claiming autonomous reporting. The
organization remains the owner of send interval, retry bounds, stale threshold,
and server policy. A stopped or sleeping device cannot send; after the
organization threshold the server projects `stale` rather than proving an
uninstall or an intentional local opt-out.

## Consequences

- Idle logged-in installations continue to report when their OS scheduler is
  available. Ordinary CLI invocations remain a second opportunity to send.
- User session and credential-store availability bound the wakeup. Headless
  Linux hosts need a running user manager and readable user credential store.
- The installed interpreter path is captured in the OS task. Re-running
  `heartbeat enable` repairs that path after moving or reinstalling the CLI.
- XDG directory paths are stored only in the local task, never in the
  heartbeat payload.
- No anonymous telemetry, runtime usage event, or heartbeat payload is added.
