---
description: "SPEC-093: Authenticated, durable facts for corporate installation operations."
last_verified: "2026-09-26"
---

# SPEC-093: Corporate installation operation facts

## Purpose

Preserve factual AI-STP installation, update, removal, and rollback outcomes for the corporate Usage report without treating a scan or heartbeat as an operation.

## Scope

The existing CLI operation journal is the local source. The authenticated corporate API stores closed operation facts. SPEC-089 governs retention and subject erasure. SPEC-088 governs invocation events, which remain independent.

## Terms

- `Corporate binding` — immutable organization, project, employee, device, and scope recorded before a provider apply.
- `Operation fact` — one settled journal operation with its actual result and exact known coordinates.
- `Delivered` — a local fact explicitly accepted or confirmed duplicate by the server.

## Requirements

- `REQ-9301`: A corporate binding is recorded before provider effects and cannot be changed later. Older unbound operations are not assigned an organization retroactively.
- `REQ-9302`: Only settled install, update, remove, and rollback operations project facts. Verified, partial, failed, stale, and rolled-back results remain distinct. A partial result does not claim complete components.
- `REQ-9303`: Facts include organization, employee, device, corporate project, harness, scope, setup identity and version when known, component identities and exact versions when recoverable, action, outcome, and time. The closed request rejects paths, secrets, task contents, arguments, and model output.
- `REQ-9304`: Intake binds employee and device to the authenticated caller, checks tenant project and revocation, rejects future and expired timestamps, and deduplicates on organization plus operation ID. A repeated ID with different content is rejected.
- `REQ-9305`: The local journal remains the retry source. Only accepted and confirmed duplicate IDs get delivery markers; rejected or unacknowledged facts remain pending. Explicit sync and an enabled heartbeat can retry them offline-first.
- `REQ-9306`: Server facts obey tenant row-level security, raw retention, and physical device or account erasure. Detailed reads must use the separate event-detail permission when exposed in the report.
- `REQ-9307`: A verified rollback recovers setup and component coordinates only from the install or update bundle reached by an exact journal chain. The selected backup reference is the digest-checked cached provider plan's `backup_ref`, not the rollback row's own backup column. Exactly one verified capturing operation in the same organization, project, account, device, target, and scope must hold that reference. Its cached native `current_digest` equals the restore plan's native `restore_digest`, and its expected target digest equals the restore plan's `restore_target_digest` and the verified target digest of the latest install, update, removal, or rollback before that capture. An install or update contributes its cached bundle, including standalone component bindings the setup passport omits. A prior rollback is followed by the same rule. A prior removal, more than one capturing operation, a partial or cross-account mutation in between, a missing artifact, a digest mismatch, or a cycle leaves the fact incomplete. Delivered facts are not rewritten. The resolver does not open provider backup slots or infer a setup from a backup label. A plan records the scope it was planned against. A sourceless corporate binding uses that scope; a plan recorded before the scope column stays unknown rather than being rewritten. Apply re-reads provider `status` at the scope the plan was made for: the bundle manifest when the plan has a bundle, otherwise the projection digest in the cached provider plan. `user_root` is resolved that way and is not written into the scope column, so its corporate binding stays unknown.

## States and errors

`partial` means the provider may have changed the target but verification is incomplete. `failed` and `stale` do not prove installation. Missing component coordinates or scope are explicitly incomplete or unknown. Failed network delivery leaves the journal fact pending.

## Security and privacy

The server derives the trusted identity from the session and rejects a body naming another employee, device, organization, or project. The fact schema has no content or path fields. The endpoint audits accepted, duplicate, and rejected counts only.

## Compatibility and migration

Local registry migration 48 adds bindings without changing old operations. Migration 50 records the planned scope on new operation plans and leaves that column out of the plan digest. A plan from before the column keeps a null scope, so a sourceless binding for it stays unknown and is not rewritten. Server migration 0097 adds the tenant-isolated fact table. Existing heartbeat and usage streams keep their own contracts. No historical event is synthesized from a later inventory scan.

## Acceptance criteria

| Requirement | Executable oracle |
| --- | --- |
| `REQ-9301` | Local journal test proves repeated matching binding succeeds and changed binding fails. |
| `REQ-9302` | Local projection test preserves partial result and incomplete component state. |
| `REQ-9303` | Strict contract test rejects undeclared content and validates exact coordinates. |
| `REQ-9304` | Intake test covers idempotency, changed-content rejection, and forged subject rejection. |
| `REQ-9305` | Delivery test verifies only acknowledged IDs are marked delivered. |
| `REQ-9306` | Retention and erasure tests include the new table; migration check verifies tenant policy. |
| `REQ-9307` | Rollback provenance tests prove exact bundle recovery, standalone bundle members, and refusal on drift, ambiguity, account change, partial interruption, self-backup, and a backup-reference cycle. Planned scope is recorded once, yields to a bundle scope, and lets a sourceless rollback recover; a missing recorded scope stays unknown. A sourceless rollback planned at `project` or `user_root` reaches verified through apply; `user_root` stays out of the corporate column. |
