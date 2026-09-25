---
description: "Opted-in installation heartbeats use per-user OS wakeups while the CLI retains due times and retries."
last_verified: "2026-09-25"
---

# ADR-0209: User-scheduled installation heartbeats

Status: accepted. Extends ADR-0208 for the case where the CLI is idle.
ADR-0211 supersedes its fixed hourly cadence.

## Context

ADR-0208 sends due heartbeats after ordinary CLI commands. An idle installation
therefore becomes stale even when the machine is on and the user remains logged
in. A Python scheduler started inside a short-lived CLI process exits with that
process; an always-running Python daemon would require another lifecycle.

## Decision

`heartbeat enable` registers an hourly per-user OS wakeup for the opted-in
organization. The wakeup invokes the due sender through the installed Python
interpreter and a small local launcher that restores the enrolled XDG
config/data directories and credential-store selection. It calls the same
SQLite due claim, organization policy lookup, fresh report assembly, and bounded retry
path as ordinary CLI invocations. `heartbeat disable` removes local opt-in
before removing the wakeup, so a removal failure cannot cause another send.
The sender does not infer opt-in from the presence of an OS task.
The scheduled launcher calls the due sender directly and does not read back
Task Scheduler state or execute harness version queries. Its report attests
CLI liveness; explicit sends retain detailed harness/provider inspection.

Windows uses a Task Scheduler task under the interactive user and `pythonw.exe`
so wakeups do not open a console, with missed-run catch-up; macOS uses a
LaunchAgent with a one-hour interval and
`RunAtLoad`; Linux uses a user `systemd` timer with `Persistent=true`. WSL
registers a Windows task that starts the named distribution and user through
`wsl.exe` via a hidden `wscript.exe` launcher, because its own systemd timer does not keep an idle WSL instance
alive. No administrator privilege, new credential, or third-party runtime
dependency is required.

The wakeup frequency is independent of the organization's send interval. The
organization may choose a send interval as low as 60 seconds, while the hourly
OS wakeup bounds autonomous reporting on an idle CLI installation. The CLI reports the local subscription,
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
