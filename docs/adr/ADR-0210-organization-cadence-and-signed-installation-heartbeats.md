---
description: "Organization heartbeat policy drives the OS timer and device keys sign reports."
last_verified: "2026-09-25"
---

# ADR-0210: Organization cadence and signed installation heartbeats

Status: accepted. Supersedes the fixed hourly wakeup in ADR-0209.

## Context

An hourly OS wakeup and an independent organization send interval can miss a
due time by almost an hour. A bearer session bound to a device identifier does
not alone prove that the request holder has the enrolled device's private key.

## Decision

The existing `telemetry_policy` row owns heartbeat enablement and the single
recurring OS timer interval. At opt-in, the CLI reads that interval and
registers the timer. Each scheduled invocation attempts one heartbeat without
applying the opportunistic CLI due-time gate. It reads policy first and repairs
the timer only when the interval changed. The next scheduled invocation sees
a policy change; no resident agent or push channel is introduced. The existing
local due time remains solely for optional sends after ordinary CLI commands.

Every heartbeat request is signed with the enrolled Ed25519 device key over
the organization ID and canonical closed request body. The API checks account
and device session binding, active device registration, signature, and a
five-minute clock window before accepting the report. Equal or older reports
remain idempotent. TLS authenticates the server's policy response; a second
server signature would add no useful trust boundary here.

The per-user scheduler remains installed when the network fails and tries
again at its next interval. Transport retries within one scheduled invocation
are bounded. Missed-run catch-up remains platform-specific. Staleness is
evaluated from server receive time and cannot prove uninstall or malicious
disablement. A device key signature proves key possession, not the integrity
of an unmanaged client process.

Scheduled sends renew the CLI session before its local expiry through a
device-signed `/auth/device/refresh` request using the stored refresh credential.
The server issues a new credential pair after verifying the enrolled key and
active session. It leaves the prior credential valid until normal expiry so a
lost response cannot strand the installation. Revoking the device still
invalidates every bound session. No refresh credential is included in a
heartbeat body, log, or ordinary local registry row.

## Consequences

- The organization can enable or disable reporting and change cadence using
  its existing database-backed telemetry policy API.
- The old cadence remains until the next policy read by an enrolled device.
- Windows scheduler helper processes use windowless creation flags; the task
  continues to use `pythonw.exe`.
- macOS reloads a changed LaunchAgent from a detached short-lived helper after
  the current tick, because booting out a running agent would stop its own
  process before it could bootstrap the replacement.
- A CLI must hold the enrolled key to send a heartbeat; older unsigned clients
  must be upgraded when the API starts enforcing signatures.
