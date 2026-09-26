---
description: "SPEC-094: Opt-in, bounded corporate installation inventory snapshots."
last_verified: "2026-09-26"
---

# SPEC-094: Corporate installation inventory

## Purpose

Record current native component observations without inventing installation operations or usage invocations.

## Scope

The existing native discovery service scans global harness configuration and linked corporate projects. The corporate API stores closed snapshots. SPEC-089 governs retention and erasure; SPEC-093 governs provider operation history.

## Terms

- `Snapshot` — one timed global or project discovery result for one employee and device.
- `Complete` — the named scope was fully examined without an unreadable or bounded continuation.
- `Unknown` — no complete successful observation can establish current presence or absence.

## Requirements

- `REQ-9401`: Inventory scanning is disabled by default and separately controlled from heartbeat enablement. A disabled scan does not block heartbeat delivery, and intake rejects snapshots while the organization has scanning disabled.
- `REQ-9402`: A scan covers global known harness configuration and locally linked corporate projects through the existing discovery mechanism. It compares the newest settled corporate provider result per target with the exact cached bundle to distinguish managed components and their versions from external components. A missing project root, incomplete discovery, or unavailable managed baseline is marked incomplete. A verified rollback uses the bundle recovered by `REQ-9307` as that baseline; an unrecoverable rollback leaves the scope incomplete.
- `REQ-9403`: Snapshot requests contain only identities, time, scope, completeness, kind, harness, digested native location, managed component and setup coordinates when verified, source classification, and observed state. They exclude absolute paths, component contents, and usage payloads.
- `REQ-9404`: A local, account-and-device-scoped outbox persists snapshots before network delivery. Only accepted or confirmed duplicate IDs are removed; rejected and unacknowledged IDs remain pending.
- `REQ-9405`: Intake checks tenant, authenticated employee, active device, active project, revocation, timestamp, and snapshot digest. Conflicting replays are rejected.
- `REQ-9406`: A complete successful snapshot can support an absence conclusion only for its own scope. An incomplete or failed scan does not delete earlier observations or prove removal. Heartbeat and inventory do not increment usage.

## States and errors

An incomplete snapshot may contain partial observations, but omission from it has no removal meaning. A failed upload remains pending. A stale complete snapshot must be shown as stale by the report rather than current confirmation.

## Security and privacy

The server derives employee and device trust from the authenticated session and stores snapshots behind tenant row-level security. The closed request has no free-text or path fields. Intake auditing records counts only.

## Compatibility and migration

Migrations 0098 and 0099 add the opt-in policy flag and snapshot table. Local registry migration 49 adds the outbox. Older clients omit the new policy flag and do not scan.

## Acceptance criteria

| Requirement | Executable oracle |
| --- | --- |
| `REQ-9401` | Policy and heartbeat tests prove default disabled and independent heartbeat delivery. |
| `REQ-9402` | Scanner tests prove missing roots and bounded discovery remain incomplete; managed comparison test detects the exact version, modification, and removal. |
| `REQ-9403` | Strict contract test rejects content and path fields. |
| `REQ-9404` | Outbox test proves selective acknowledgement. |
| `REQ-9405` | Service test proves idempotency and forged subject rejection. |
| `REQ-9406` | Report test proves incomplete scans cannot create a removal conclusion. |
