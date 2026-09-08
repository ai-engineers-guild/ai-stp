---
description: "Machine boundary for ai-stp CLI self-update: commands, plan fields, journal states."
last_verified: "2026-09-08"
---

# CLI self-update

Requirements owner: `SPEC-072`. Decision: `ADR-0170`. Field list for
notifications and channel: `cli-config.md`. Error codes: the foundation
registry.

This document names the machine surface. It does not restate PEP 440 or the
PyPI Index API.

## Commands

| Command | Mutability | Result schema |
|---|---|---|
| `update check` | read | `urn:ai-stp:schema:v1:cli-self-update-check` |
| `update plan` | plan | `urn:ai-stp:schema:v1:cli-self-update-plan` |
| `update apply` | apply, confirmation `plan_digest` | `urn:ai-stp:schema:v1:cli-self-update-result` |
| `update status` | read | `urn:ai-stp:schema:v1:cli-self-update-status` |
| `update recover` | apply | `urn:ai-stp:schema:v1:cli-self-update-result` |
| `update rollback` | apply, confirmation `plan_digest` | `urn:ai-stp:schema:v1:cli-self-update-result` |

`expected-plan-digest` on apply/rollback is the digest returned by the matching
plan. Recover continues the journalled plan and does not take a new digest from
the caller.

## Install methods

`uv_tool` | `pipx` | `pip_venv` | `shared_environment` | `system_environment` | `source_managed`

`INSTALLER` inside dist-info is not sufficient to distinguish `uv tool` from
`uv pip`. Detection uses receipt, install root and executable identity.

## Check states

`current` | `available` | `unknown` | `stale` | `unsupported` | `source_managed`

`available` requires the candidate to be present on both the JSON API and the
install-visible Simple Index with matching filename and sha256.

## Journal states

`idle` | `planned` | `downloaded` | `applying` | `pending` | `verified` |
`recovery_required` | `rolled_back` | `failed`

`pending` means a helper still running outside this process. `verified` is the
only successful replacement.

## Local files

All under `${XDG_DATA_HOME}/ai-stp/self-update/`, separate from the registry
SQLite file, secrets and telemetry. The check cache may be written by an
otherwise read-only invocation. Plans, staged wheels and rollback wheels are
owner-only.

## Notifications

TTY human mode uses the existing `warning:` stdout channel. Machine mode puts
the same sentence in `warnings` and adds `update plan --json` to `next_actions`.
The updater never writes a second JSON object or reads stdin.
