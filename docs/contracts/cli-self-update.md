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

`pending` means a standalone standard-library helper is continuing outside the
replaced Python prefix, on every supported OS. The helper takes the same update
lock after the initiating process releases it; it owns installer execution and
new-process verification. A pending response acknowledges handoff only. `verified` is the
only successful replacement. Recovery reconciles the installed target before
repeating an installer. Replaying a verified replacement returns `unchanged`.
A new plan never overwrites an active or recoverable journal. Rollback journals
retain their direction through failures; recovery resumes that same rollback.
Rollback digests bind the retained wheel receipt, and bytes are rehashed before
installation. A changed or unobservable version cannot report `rolled_back`.
Rollback also binds the configured registry path into the continuation and reads
its SQLite schema without migrating it. The hash-verified retained wheel's
`ai_stp_cli/local/database.py` declares the supported ceiling: an integer
`SCHEMA_VERSION` or the final version in its ordered literal `MIGRATIONS` tuple.
The declaration is parsed without executing wheel code; an unknown declaration
cannot establish compatibility. A newer registry refuses replacement; the
helper repeats the check before invoking the installer and before recording
success. Backups are retained, not rewound implicitly.
SQLite backups use the online backup API to include committed WAL content.

## Local files

All under `${XDG_DATA_HOME}/ai-stp/self-update/installations/<prefix-sha256>/`,
where the installation key hashes the resolved interpreter prefix, separate from the registry
SQLite file, secrets and telemetry. The check cache may be written by an
otherwise read-only invocation. Plans, staged wheels and rollback wheels are
owner-only.

## Notifications

TTY human mode uses the existing `warning:` stdout channel. Machine mode puts
the same sentence in `warnings` and adds `update plan --json` to `next_actions`.
The updater never writes a second JSON object or reads stdin.

The notice cache is matched to installation, version and channel. Startup checks
share one deadline across index calls. A backoff suppresses subsequent startup
checks, and a notification is emitted once per candidate digest. Explicit checks
can refresh the index; offline checks use only matching stored facts.

Downloads are written to a private temporary file and renamed only after the full
planned size arrives. Interrupted download bytes never occupy the staged wheel
name. Only HTTPS index/artifact endpoints are used and redirects are not followed.
Apply rechecks the exact target against current index metadata, not a new latest.

Plans bind the owning installer's non-secret environment roots in
`installer_environment`. Only UV_TOOL_DIR, UV_TOOL_BIN_DIR, PIPX_HOME and
PIPX_BIN_DIR may be supplied there. The uv installer also pins the current base
interpreter. Continuation files are private, checksum-bound and retained beside
the installation journal so recovery does not depend on the replaced package.
