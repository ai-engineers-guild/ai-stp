---
description: "Business disposition of the historical Python CLI inventory at the native release cutover."
last_verified: "2026-10-14"
---

# Native CLI scope reconciliation

The frozen [Python inventory](cli-v2-baseline.json) records 245 commands and nine
intents at `7220c991ac7ef3be7d23357a7e24739a20ae860d`. It is migration evidence,
not the current command registry. Its original `retain` values are historical;
this document records the resulting business disposition. Current parameters
come from Rust `help --agent --json`, not aliases for the old parser.

The primary consumers were the agent control procedure and desktop. The native
procedure discovers implemented services; desktop now consumes native descriptors,
account plans and author/install task inputs. No caller falls back to Python.
Historical passports, versions, evaluation records and settled task receipts remain
in the original database; absence of an old command does not delete those rows.

| Historical family | Leaves | Native disposition and evidence owner |
|---|---:|---|
| Orientation | 15 | `version`, `capabilities`, `help`, `doctor`, `init`, `state path`, `config show/validate` and `environment requirements`. Machine help replaces duplicate inventory/schema/link wrappers. Only implemented network configuration is exposed; no unused update/telemetry/provider-path settings. `tests/startup.rs`, `scripts/verify.py` |
| Identity and access | 21 | `device initialize`, `device show`, `account plan/apply/status`, `grant plan/apply/list`, passport plans and `local apply`. Account attachment/recovery, access grants and per-operation access checks replace separate login/consent wrappers. `identity`, `account`, grant proofs and `verify_migration.py` |
| Catalog and sources | 17 | `registry search/show/version/acquire plan`, source inspection/fetch/capture/address parsing and local discovery. Acquired public/private bytes retain exact source/provenance; no separate generic remote port manager. Catalog/source tests and real API qualification |
| Authoring | 29 | Component/setup plans, immutable versions, import/export, adaptation/materialization and `local apply`. Transformations are registered only for implemented native surfaces; unsupported transformations refuse. `authoring`, `objects`, source and setup tests |
| Projects | 12 | Bounded discovery/index/symbols, project passport and explicit installation attribution. Corporate organization link/unlink workflows are excluded; local physical project binding remains. Project and selection tests |
| Technology | 17 | Local `project technology inspect/plan/findings` retains observed evidence. Corporate mapping administration, remote taxonomy publication and organization-specific override workflows are excluded. Project technology proofs |
| Selection | 11 | Graph, eligibility/matrix, impact/blast-radius, proposal/confirmation/cancellation, reports and deterministic scoped bundles. Exact coordinates, installed harness identity and access/trust remain mechanical preconditions. Selection/bundle tests |
| Installation and recovery | 25 | `configuration` and complete `configuration set` plan/prepare/apply/confirm/cancel/status, plus `install` tasks. One to three roots, partial publication recovery and active Linux handoff share one coordinator. Automatic backup/preserve/rollback wrappers are retired under the owner's no-backup requirement; removal/replacement and forward recovery remain explicit. Provider tests and real process termination/handoff evidence |
| Software lifecycle | 27 | Authenticated managed setup-component acquisition, `provider inspect/status/plan/network` and read-only `program status`. Harness executable lifecycle is retired by ADR-0232. Standalone package execution, generic toolchain management and independent skill installation are not native services; setup content is assembled and installed through its provider. Existing standalone CLI artifacts remain authorable data, not an implicit executable authority |
| Synchronization | 8 | `sync preview`, merge/push/pull/recover plans, `sync apply` and retained conflicts. Project/developer/device content uses the same identity-bound exchange; explicit `sync.enabled` is required. Sync tests and real API qualification |
| Publication and distribution | 14 | Publication plan/resume/apply/status/reconcile, visibility plans, GitHub source plans/status and catalog readback. Accepted asynchronous work is distinct from verified publication. Publication/account tests and real API qualification |
| Assurance | 15 | Passport validation/quality, exact graph/bundle checks, author attestation and contribution reports. The old static evaluation wrappers are consolidated into these checks; model/human runner placeholders are not advertised as an execution service. Historical evaluation rows are preserved, with no invented verification flag. Authoring, selection, attestation and report proofs |
| Governed operation | 21 | Corporate assignments, heartbeat, telemetry consent and usage delivery are excluded by the owner. No native scheduler or delivery hook replaces them |
| Task interface | 7 | Start/answer/continue/cancel/status/list/intents remain, with `input-schema`. Implemented intents are `author` and `install`; account, initialization, publication and inspection use their direct native services. Install covers explicit install/replace/remove and optional handoff. Old settled tasks stay read-only; unfinished legacy tasks block transfer |
| CLI lifecycle | 6 | `cli install plan/apply/status` installs and updates a verified archive into its own prefix. Exact readback and forward recovery replace interpreter-owned update wrappers. Other owners are not overwritten; version/database rollback is refused. `tests/distribution.rs` and extracted-archive CI |

This is a clean business implementation, not command-count parity. The release
boundary excludes a new corporate product, model interfaces, automatic backups,
generic software management and a backend rewrite. The user's release decision
accepts working macOS/Windows CI without extending the Linux provider sandbox to
those platforms. Their unsupported configuration operations remain explicit
refusals and are reported by `capabilities`.

## Runtime and validation ownership

One Rust package owns services; command and task adapters call them in process.
Desktop remains a subprocess client. The API, worker and shared Python packages
keep their current ownership. `apps/cli` is retained only as a development
compatibility oracle and historical-state fixture source; native artifacts have
no Python dependency or fallback. The historical wheel release lane is retired.

The code-adjacent [CLI guide](../../apps/cli-v2/README.md) owns current installation,
state-transfer and platform limits. The affected gates are `just cli-v2-check`,
`just desktop-check`, documentation checks and the tag-bound three-platform
archive workflow. Exact observed runs and real API/provider evidence belong to
[#57](https://github.com/ai-engineers-guild/ai-stp/issues/57) and the release PR.
A green compile does not claim unexecuted platform/provider behavior.
