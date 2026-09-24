---
description: "Opt-in installation heartbeats are retried opportunistically by the CLI and use organization telemetry policy."
last_verified: "2026-09-24"
---

# ADR-0208: Periodic CLI installation heartbeats

Status: accepted. Builds on ADR-0204 and ADR-0205; governed by SPEC-013 and
SPEC-089. ADR-0209 extends its invocation-only trigger with per-user OS wakeups.

## Context

The authenticated heartbeat route and read-time health projection exist, but a
user must invoke `heartbeat send` manually. The CLI currently declares every
supported harness as a capability without checking which local harnesses have
a usable provider. The server also applies the same 24-hour staleness threshold
to every organization, and the coalesced heartbeat row is outside the telemetry
retention worker.

An always-running daemon would keep an otherwise idle machine reporting alive,
even when no `ai-stp` operation is occurring. It also requires separate service
installation, shutdown, credential-refresh, and recovery behavior on every
supported operating system.

## Decision

After explicit per-organization opt-in, the CLI checks whether a heartbeat is
due after a successful ordinary `ai-stp` invocation. It sends at most one
current snapshot per subscribed organization per invocation. Heartbeat and
authentication commands do not recursively trigger this path. Reporting is
best-effort: transport, auth, or local-state failure never changes the result
of the command the user invoked.

The CLI stores only the organization subscription and bounded scheduling
metadata locally: enrolled account/device, last attempt, last success, and next
retry. The account/device binding prevents a changed local session from
inheriting an earlier opt-in. It does not keep an offline payload queue. A
later attempt builds a fresh snapshot and uses the existing server coalescing
key, so delayed reports cannot replace newer state.
The registry migration is additive: an older CLI can ignore the subscription
table during rollback, so the schema marker may step back without deleting
opt-in state. A later upgrade reuses that table.
Retry delay is bounded by the organization policy and uses backoff; an expired
session defers reporting until the user next authenticates. At most one due
organization is attempted per ordinary invocation, choosing the oldest due
subscription first, so a large subscription set cannot make every CLI command
wait on a long network batch.

The existing organization telemetry policy owns whether reporting is allowed,
the heartbeat interval, retry bounds, stale threshold, and retention. Defaults
preserve the current 24-hour stale threshold and 90-day raw retention. The
existing raw-retention period also applies to coalesced heartbeat rows; the
retention worker deletes rows past that period but never writes `stale`. A
deleted row projects as `unknown`.

The heartbeat reports only local provider facts that can be established without
running provider code: whether a provider executable resolves for a locally
installed harness and, when the installed artifact digest matches its local
release manifest, its declared provider identity and version. Paths are never
sent. An unverified or ambiguous executable is not reported as available.
This check does not claim that a provider process or the harness itself is
currently running.

Server writes honor telemetry revocation and organization disablement before
mutating the coalesced row. A CI runner may report through the same enrolled,
device-bound CLI session as an interactive machine; no separate service
principal or unbound CI token is added. Heartbeats remain separate from
component invocation events and emit no usage event.

## Consequences

- Without an OS wakeup, a device reports only while `ai-stp` is invoked and its
  local subscription is enabled. ADR-0209 adds a per-user wakeup for idle CLI
  installations; there is still no always-running Python daemon.
- Local opt-out is explicit and reversible. Organization policy can stop all
  further reporting and controls timing and retention centrally.
- Provider readiness claims are bounded to verified on-disk evidence; no
  provider is executed as a side effect of a heartbeat.
- CI runners are covered only when they use an enrolled CLI installation and
  its device-bound session. A distinct service-principal authentication flow
  is outside this issue.

## Revisit conditions

Require a heartbeat while the CLI is idle; require live provider-process or
managed-check verification; or retain CI service identities in issue #215's
acceptance criteria.
