---
description: "SPEC-072: Self-update of the installed ai-stp-cli distribution via PyPI."
last_verified: "2026-09-08"
---

# SPEC-072: CLI self-update through PyPI

## Purpose

An installed `ai-stp-cli` can discover a newer compatible wheel on PyPI, describe
an exact replacement, apply it through the installer that owns the installation,
and recover or roll back without destroying local data.

## Scope

Included: `ai-stp update check|plan|apply|status|recover|rollback`, startup
notifications, install-method detection, exact artifact pinning, and preservation
of auth, device, config, registry (including WAL), downloads, preserved setups
and provider backup pools.

Excluded: provider/harness/setup updates, reinstalling retired internal PyPI
projects, system-wide package upgrades, and adding updater behaviour to already
published wheels that do not contain this command family.

## Terms

- Distribution — the public `ai-stp-cli` wheel with bundled first-party
  namespaces (`ADR-0146`).
- Install method — `uv_tool`, `pipx`, `pip_venv`, `shared_environment`,
  `system_environment`, or `source_managed`.
- Exact plan — source and target versions, interpreter, method and prefix,
  artifact filename/size/digest, index origin, channel, installer argv, restart
  and rollback facts. A later index latest does not replace those bytes.
- Channel — `stable` excludes PEP 440 pre-releases; `prerelease` includes them.
  Local/dev versions are never selected from the index.

## Requirements

- `REQ-7201`: Interactive TTY may show one short notice of a newer compatible
  version and the update command. The notice does not change the original
  command's exit status or prompt. `--json`, pipes and non-TTY receive the same
  fact only as envelope `warnings` / `next_actions`. Stdout stays one envelope.
- `REQ-7202`: A network check is bounded (startup total ≤500 ms, TTL default 24
  hours, backoff after 429/5xx/timeout). Fresh cache does not contact the index on startup; explicit `update check`
  refreshes the index.
  Offline, timeout, 429, 5xx, TLS failure, invalid JSON, oversized body and
  corrupt cache do not fail the original command and do not mean "no updates":
  state is `unknown` or `stale`.
- `REQ-7203`: `update check` reports installed distribution, interpreter, method,
  executable, candidate, compatibility, cache age and the reason if nothing is
  offered. `update plan` pins one exact artifact. `apply` reapplies that digest
  only. JSON API ahead of Simple Index is not install-ready.
- `REQ-7204`: Versions compare by PEP 440. Selection honours `Requires-Python`,
  wheel tags, yanked files, channel and an explicit `--version`. A yanked,
  disappeared or hash-changed file refuses; it is not replaced by a new latest.
- `REQ-7205`: Apply uses the owning installer. `uv_tool` and `pipx` are updated
  through those tools. A dedicated pip venv is updated through that interpreter.
  Shared/system environments are not mutated; the plan names a migration to a
  dedicated tool environment. Editable/`uv run` checkouts are `source_managed`
  and are not replaced by a wheel. Shadowed PATH copies are reported. After
  replacement a new process must observe the target version.
- `REQ-7206`: Apply is exclusive, does not run inside another mutating install,
  publication confirm or recovery of a different subject, and does not auto-start
  from a notice. SQLite backup includes WAL. Auth, device, config, registry,
  downloads, preserved setups and provider backups are retained. Durable journal
  states are `planned`, `downloaded`, `applying`, `pending`, `verified`,
  `recovery_required`, `rolled_back`, `failed`. `ok` on `pending` means the
  handoff was accepted, not that the new CLI is verified.
- `REQ-7207`: `status` is a new process reading the journal and the installed
  distribution. `recover` finishes or restores without repeating a verified
  effect. `rollback` restores the previous verified distribution when the data
  schema remains compatible. Missing rollback bytes are a typed refusal.
  The retained wheel's supported registry schema is checked against the current
  SQLite header before replacement and rechecked by the standalone helper.
  A migrated registry newer than that reader refuses rollback before the
  installer runs. A changed schema during replacement cannot report success.
  Saved data backups are never restored implicitly to make a binary rollback
  possible; post-update user writes remain intact.
- `REQ-7208`: A Windows helper, when required, runs outside the replaced prefix.
  Linux and macOS paths with spaces or Unicode remain valid. Two concurrent apply
  operations contend on one lock.

## States and errors

`AI_STP_PRECONDITION_FAILED` — unsupported/shared/system/source-managed apply,
incompatible Python, missing rollback bytes, installer absent.
`AI_STP_PLAN_STALE` — digest mismatch, vanished or yanked artifact.
`AI_STP_CONFLICT` — update lock held or another mutating operation in progress.
`AI_STP_DEPENDENCY_UNAVAILABLE` — index/installer unreachable on an explicit
check that cannot use cache; startup notice still degrades to `unknown`.
`AI_STP_RATE_LIMITED` — 429 with Retry-After recorded as backoff.
`AI_STP_VALIDATION_ERROR` — bad channel, version, or hash.
`AI_STP_NOT_FOUND` — requested version absent from both JSON and Simple Index.
`AI_STP_TIMEOUT_UNCONFIRMED` — installer handoff still pending.
`AI_STP_PARTIAL_OPERATION` — apply interrupted; journal is `recovery_required`.

## Security and privacy

Index URLs and installer argv contain no secrets. Credential stores and `.env`
are not copied into plans, journals or notices. Wheel bytes are hashed before
the installer runs. Provenance, when present, is checked; its absence is
reported and does not by itself authorize apply on a hash-verified public wheel.
HTTPS, bounded size and redirects; index documents are not executed.

## Compatibility and migration

Wheels published before this specification cannot emit the notice. The first
upgrade from `0.0.17`/`0.0.20` is a one-time installer bootstrap to an
updater-enabled release. Subsequent upgrades use this command family.
Configuration keys `update.enabled`, `update.channel`, `update.check_ttl_hours`
and `update.notifications` default to a working check on `stable`.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-7201` | TTY notice on an old install; JSON/pipe: one envelope, no prompt, exit unchanged |
| `REQ-7202` | Offline/429/timeout/corrupt cache: original command succeeds, state `unknown`/`stale` |
| `REQ-7203` | Plan digest unchanged when a newer version appears between plan and apply |
| `REQ-7204` | Yanked, prerelease-on-stable, unsupported Python, local version: correct refusal/reason |
| `REQ-7205` | uv tool pin, pipx and dedicated venv each replace the selected executable |
| `REQ-7206` | Kill during apply leaves a recoverable journal; data files survive |
| `REQ-7207` | Rollback restores a compatible previous version; a newer SQLite schema refuses before installer execution, and a schema changed during replacement cannot report success. The standalone helper repeats the check. A real isolated uv-tool update/rollback retains registry rows and confirms the version from fresh processes. |
| `REQ-7208` | Concurrent apply: one lock holder, the other `AI_STP_CONFLICT` |
