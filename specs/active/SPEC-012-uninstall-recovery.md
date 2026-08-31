---
description: "SPEC-012: Uninstallation, full cleanup, and recovery."
last_verified: "2026-08-03"
---

# SPEC-012: Uninstallation, full cleanup, and recovery

## Purpose

The user can uninstall the `ai_stp` executable layer, retain their data for reinstallation, perform a full cleanup separately, and recover the harness after a partial operation without guessing the last state.

## Scope

This includes regular uninstallation, `--purge`, separate cleanup of target directories and backups, stale plans, recovery after a partial operation, and reinstallation. Automatic deletion of provider backups and irreversible actions without a plan are out of scope.

## Terms

- `uninstall` — removal of the CLI, providers, toolkit, control skills, and credentials while retaining user data.
- `purge` — a separate, confirmed cleanup of the local registry and user data.
- `recovery report` — the exact last verified state and the permitted next actions.

## Requirements

- `REQ-1201`: Regular uninstallation removes the CLI, providers, managed toolkit, integration skills, and local cloud credentials.
- `REQ-1202`: Passports, the registry, drafts, artifacts, targets, and provider backups are retained during regular uninstallation.
- `REQ-1203`: Full data cleanup is performed as a separate operation after a side-effect-free plan and user confirmation.
- `REQ-1204`: Harness target directories and backup bytes require a separate destructive operation and are not silently included in general cleanup.
- `REQ-1205`: An expired or changed plan is not applied.
- `REQ-1206`: A partial apply or removal persists a durable operation and produces a recovery report instead of retrying automatically.
- `REQ-1207`: Recovery uses the exact `BackupRef`, provider version, and target identifier. The reference is read by a command after the copy operation, not only from its response; the recovery plan is bound to the `BackupRef` and target and does not require naming a setup or proposal.
- `REQ-1208`: Reinstallation detects the retained registry and offers recovery without changing the target.
- `REQ-1209`: Recovery restores the entire `HarnessTarget` from the exact backup reference; partial recovery of an individual component is not supported.
- `REQ-1210`: Before recovery, a plan showing the current active and target versions is displayed, and after the operation the state is verified; failed recovery retains `partial` and the last verified state without retrying automatically.

## States and errors

Operations use the common state set for mutating operations from `docs/contracts/operation.md`, where `verified` is the only success state name; there is no separate `succeeded` operation state. Cleanup distinguishes access revocation, a logical deletion marker, and physical deletion. An unknown provider version or missing backup blocks recovery with an exact error code.

## Security and privacy

The plan lists every system-owned path and excludes user data. Symlink escape and races with an active provider operation are blocked. Credentials are removed without printing their values. Local full cleanup does not affect cloud data without a separate server request.

## Compatibility and migration

The ownership manifest and operation journal are versioned. A new CLI reads supported older manifests. Migration and recovery must be verified before removing an old parser. Provider rollback does not depend on the newest available version.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1201` | An uninstall test confirms removal of owned executable paths and credentials. |
| `REQ-1202` | A snapshot test confirms retention of the passport, registry, draft, target, and backup references. |
| `REQ-1203` | Full cleanup without a valid plan and confirmation is rejected. |
| `REQ-1204` | A separate target test lists and deletes only explicitly selected targets and backups. |
| `REQ-1205` | A changed ownership manifest makes the plan stale. |
| `REQ-1206` | Fault injection after each step creates a resumable recovery report. |
| `REQ-1207` | A recovery test uses the exact provider release and backup identifier; backups for the pair are listed by a read command in creation order, an incomplete operation does not offer a backup, a backup for another pair is not offered, and the `rollback` plan is built without `--setup` and `--proposal`. |
| `REQ-1208` | Reinstallation attaches the registry without changing the target. |
| `REQ-1209` | A request to recover one component is rejected with a typed error. |
| `REQ-1210` | Recovery fault injection retains `partial` and does not start a retry automatically. |
