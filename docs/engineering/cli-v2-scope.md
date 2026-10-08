---
description: "Code-derived business scope, compatibility risks and baseline evidence for the Rust CLI migration."
last_verified: "2026-10-07"
---

# Rust CLI v2 scope and evidence

This is the frozen C0 design and evidence record for
[#57](https://github.com/ai-engineers-guild/ai-stp/issues/57), before the first
Rust slice. Current native preview behavior belongs to `apps/cli-v2` and its
code-adjacent README. Python CLI 0.0.43 remains the production runtime.
[ADR-0227](../adr/ADR-0227-rust-cli-v2-migration-boundary.md) owns the migration
boundary. The [implementation roadmap](implementation-roadmap.md) is the sole
ordered plan; this document explains what that plan must preserve and prove.

## Reproducible scope

The baseline is the code at
`7220c991ac7ef3be7d23357a7e24739a20ae860d`, after the October 7–8 stabilization
audit. It has 245 registered leaf commands in 38 families, nine shipped task
intents, 234 CLI Python files and 90,881 physical Python lines including
comments and docstrings. File/line counts exclude shared packages and tests;
they are neither a feature count nor an effort estimate.

The [machine ledger](cli-v2-baseline.json) records every command's handler,
descriptor digest, task classification, business group and initial disposition.
It was extracted from `ai_stp_cli.registry.COMMANDS` and `application.inventory`,
not inferred from a directory list or old specifications. The registry digest is
`sha256:e8ecda2ee31f601ddbb2161fc22e09081d273ee40f752dbe42a3a7301b141475`.
The database count comes from opening a disposable registry through the actual
`local.database.open_registry`: schema 53, 53 migrations and 51 application
tables, excluding SQLite's internal tables.

This JSON is frozen evidence, not a generated runtime registry. Its descriptor
and record hashes are plain SHA-256 over project canonical JSON; the record hash
excludes `record_digest`. They are evidence checksums, not new product digest
domains. Verify them against the recorded source revision. A later v1 change
requires an explicit ledger reconciliation, not regeneration that hides a
missing feature. The live v2 registry must describe only code it implements.

The baseline classifications are 34 `task_covered`, 128 `task_pending`, 60
`expert`, 23 `inspect`, and zero `obsolete`. `task_pending` means the command
does not yet have full high-level intent coverage; it does **not** mean the
command is unimplemented. The shipped intents are `inspect`, `initialize`,
`install`, `change`, `author`, `switch`, `account`, `publish`, and `technology`.
Porting only those nine names would not preserve the whole CLI.

## Business functions

The groups below partition all 245 commands once. They describe user outcomes,
not a requirement to create 15 crates or copy the 38 command families into
domain modules. The task interface orchestrates these same functions.

| Function | Leaves | Outcome and boundary |
|---|---:|---|
| Orientation | 15 | Explain capabilities, schemas, configuration and environment; diagnose readiness and produce web links. Static metadata needs no network or device initialization. |
| Identity and access | 21 | Maintain developer/device identity, sign-in, grants and consent. Preserve keychain ownership, revocation and exact access checks. |
| Catalog and sources | 17 | Search, inspect and acquire exact objects from supported sources; retain source evidence, cache integrity and offline behavior. |
| Authoring | 29 | Discover/adopt, scaffold, validate, adapt, version and exchange components/setups. Preserve immutable public versions and the closed component vocabulary. |
| Projects | 12 | Discover/index projects, maintain passports and explicit links/unlinks; do not claim unrelated directories or secrets. |
| Technology | 17 | Resolve evidence-backed technology facts, mappings and overrides, including publication and retirement. Do not replace provenance with inferred certainty. |
| Selection | 11 | Explain eligibility/impact, select exact versions and compile bundles. Mechanical constraints remain authoritative. |
| Installation and recovery | 25 | Plan/apply single- or multi-root changes, observe drift, preserve/restore setups and recover/roll back. Providers alone write final harness state. |
| Software lifecycle | 27 | Acquire/verify providers and manage harnesses, toolchains, standalone CLI components and control skills. Artifact trust and installer ownership are separate obligations. |
| Synchronization | 8 | Exchange private state and project revisions, detect conflicts and apply explicit merges without losing local operations. |
| Publication and distribution | 14 | Publish exact versions, manage ownership and visibility, prepare GitHub sources and read back terminal results. A queued receipt is not catalog availability. |
| Assurance | 15 | Run declared component/setup evaluations, sign author attestations and submit/read contribution reports. Author verification is independent of component verification. |
| Governed operation | 21 | Consume existing Corporate assignments and consented heartbeat/usage/telemetry policy. This preserves CLI adapters, not a rewrite of Corporate services. |
| Task interface | 7 | Start, answer, resume, cancel and inspect durable tasks over the same services, with bounded continuations and truthful terminal states. |
| CLI lifecycle | 6 | Plan/check/apply/recover/roll back the CLI through its installer, including an interrupted update and an active agent handoff. |

Every row in the ledger initially says `retain`: current code supplies no
`obsolete` set justifying bulk removal. This is a compatibility default, not a
promise to preserve internal APIs, Python layout or redundant UX forever.
Before changing a leaf, record the old outcome, actual consumers, chosen new
behavior, compatibility path and proof. An alias is justified by a consumer,
not added automatically to preserve every incidental implementation detail.

## Decisions and migration risks grounded in code

| Evidence in the current implementation | Consequence for v2 |
|---|---|
| `application/task.py` already calls application services with durable claims/leases. | Keep one business engine behind task and expert adapters; no nested CLI subprocess to reuse internal logic. |
| `registry.py` owns lazy handlers and descriptors; `foundation/envelope.py` owns JSON results and continuations. | Preserve one truthful registry and one envelope on stdout; diagnostics stay on stderr. Continuation `argv` excludes the executable and must run through the selected engine without evaluating a shell string. |
| `foundation/canonical.py` adds NFC to RFC 8785 and rejects duplicate keys, normalization collisions and invalid input. `digests.py` separates domains. | Compare exact canonical bytes and every used digest domain across languages, including number/Unicode edge cases. `serde_json` plus sorted keys does not establish equivalence. |
| `local/database.py` uses WAL, foreign keys, full synchronization, bounded lock waiting and newer-schema refusal. | Exercise backup/read compatibility, contention and interrupted journal recovery on real SQLite before production writes. Language replacement is not a storage redesign. |
| `provider/verification_runtime.py` provisions pinned Python for `index_attestation.py`; provider acquisition defaults to PyPI. | Native execution is unresolved until the full PEP 740/Sigstore identity and signature policy is proved without that runtime. Rust crate availability alone is not evidence. |
| `provider/protocol_v3.py`, invocation and OS launchers enforce process/network boundaries. | Retain bounded input/output, deadlines, cancellation, child cleanup and platform isolation. A successful JSON response alone cannot prove a safe provider invocation. |
| `self_update/` delegates to the installed wheel's owner and keeps recovery outside its prefix. | Design native distribution and ownership explicitly, including legacy installer coexistence, executable locks, journal continuity and post-update readback. |
| `app.py` may send a due heartbeat and check update notices after ordinary commands; heartbeat can refresh credentials. | A command classified as a read is not automatically side-effect-free. The v2 metadata fast path is an intentional behavior decision; preserve policy delivery through a separately bounded implemented lifecycle. |
| `application/initialize.py` checks provider capabilities before patching an instruction region. | Test the exact pinned provider's advertised capabilities and real plan/apply behavior. A schema that permits the field does not prove that every provider advertises it. |
| `application/publish.py` resumes durable plans and distinguishes accepted jobs from readable published versions. | Prove repeat/retry/restart and final provenance-bound readback; do not reduce publish to one HTTP POST. |
| Desktop `core/src/cli_runner.rs` prefers the bundled executable over configured/PATH alternatives. | Test an actual preview package/sidecar replacement. Setting a CLI path alone does not prove that a packaged desktop invokes Rust. Keep the CLI process boundary. |

These are observed dependencies and migration traps, not newly reproduced
production defects. The C0 audit does not claim every one of the 245 leaves was
executed on every OS. Inventory completeness and behavioral parity are different
evidence. Before each slice, trace its concrete handlers, schemas and consumers;
exercise real business scenarios and reconcile any conflict with the current
code before changing a specification.

## Runtime structure and dependency discipline

The initial implementation should use functional modules within one package:
CLI adapters and registry; application operations; validated domain values;
SQLite/filesystem/credential/provider/HTTP adapters. Keep side effects explicit
at the operation boundary. Do not create an interface per entity, generic
repository layer, plugin protocol, background service or speculative workspace
crate. Split a module only when it has a concrete owner and independent reason
to change.

At C0, Rust 1.99.0 was available in this checkout; that observation did not pin
the future toolchain. C0 assigned the first code checkpoint to select a stable
toolchain and the smallest required dependencies, verify their current official
documentation and supported targets, and record an upgrade/removal owner.
Resolve parser/descriptors, canonical JSON, bundled SQLite, OS credential access,
bounded HTTP/process execution and provenance separately against their actual
contracts. Do not add all prospective libraries in the first commit.

The preview reads only explicit isolated state; any v1 snapshot import checks
its source and backup digest first. Never copy secrets into fixtures or evidence.
The production switch must account for keychain identity, persistent object
paths, pending tasks, provider backups and legacy writers together. Restoring
an earlier database after later harness writes is not a valid rollback.

## Performance baseline and acceptance method

On Linux x86_64, CLI 0.0.43 was measured with seven alternating fresh processes
per command, separate empty XDG configuration/data directories and existing OS
caches. The host was shared (load averages roughly 2.5–4.6); caches were not
dropped. Every listed invocation included `--json` and succeeded.

| Command | Median wall time | Observed range | Median user CPU | stdout bytes |
|---|---:|---:|---:|---:|
| `version` | 0.667 s | 0.622–1.027 s | 0.602 s | 467 |
| `capabilities` | 0.747 s | 0.655–0.858 s | 0.670 s | 5,969 |
| `task intents` | 1.786 s | 1.707–2.380 s | 1.679 s | 6,985 |
| `help --agent` | 0.740 s | 0.705–0.839 s | 0.660 s | 256,249 |

This is a dated startup baseline, not a portable SLA or a network/provider
benchmark. A smaller preview command registry is not a fair full-help speedup
comparison. For release decisions, run at least 30 interleaved measurements of
equivalent completed behavior on the same host; record p50/p95, CPU, peak RSS,
binary size, output volume and environment. Check metadata with network denied
and without Python on PATH. Check packaged desktop startup separately.

The first native metadata target is p95 below 100 ms on the same Linux host
under a comparable load, using an optimized build and fresh processes. This is
an engineering target, **not an observed result or a cross-platform promise**.
If it is missed, profile the actual work before adding concurrency or caching.
Provider/network work retains explicit timeout and memory bounds and is measured
separately; faster startup does not excuse changed outcomes or stale evidence.

## Small proof set

Keep a few reusable suites, each covering a different failure boundary:

1. Cross-language contract vectors: canonical bytes, domain digests, validation,
   error envelopes, registry/continuations and immutable exact versions.
2. Real local state: schema-53 snapshot reads, supported migration, unknown-newer
   refusal, file permissions, atomic replacement, concurrent claims and recovery
   after interruption. Fault injection happens at an actual I/O boundary.
3. Provider and installer boundary: signed versus tampered artifacts and wrong
   publisher, bounded process execution, cancellation/cleanup, stale plan,
   partial multi-root apply and restore, active-target handoff.
4. Complete journeys over real local services and the actual `/v1` app: author
   → select → temporary-target install → recover; account → sync conflict →
   publication readback; update → interruption → rollback. External services
   may be controlled at their real transport boundary.
5. Packaged Linux x86_64, Windows x86_64 and macOS arm64 smoke/recovery evidence,
   including the desktop's real child environment and sidecar selection.

These are proof responsibilities, not five individual tests or a coverage
quota. Parameterize shared vectors instead of duplicating implementation tests.
Keep legacy checks until equivalent responsibility is proved, then remove
superseded CLI-only tests with their code. Server/shared-package tests remain.
No new tests are needed merely to freeze the wording of this design document.

## Research and limits

Primary sources were read October 7–8, 2026; their current contents are not a
reconstruction of the earlier requested September 26 snapshot.

- [Cargo workspaces](https://doc.rust-lang.org/cargo/reference/workspaces.html):
  a workspace coordinates packages and a shared lockfile; it does not require
  creating separate packages for every capability. The one-package choice is
  this project's design judgment.
- [Rust CLI testing](https://rust-cli.github.io/book/tutorial/testing.html):
  exercise the executable and its observable output/error behavior.
- [SQLite online backup](https://sqlite.org/backup.html) and
  [WAL](https://sqlite.org/wal.html): use a consistent backup mechanism and
  preserve one-writer assumptions. The documented WAL-reset defect was fixed
  in 3.51.3 and selected backports; the audited Python runtime uses 3.53.1.
  Verify the SQLite version actually bundled into Rust rather than assuming
  the crate's release date proves the fix.
- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.txt): JCS does not normalize
  Unicode. Project NFC normalization and domain separation are additional
  requirements owned by current code.
- [PyPI attestations](https://docs.pypi.org/attestations/): verification binds
  artifacts and publisher identity, not merely a downloaded checksum.
- [sigstore-rs](https://github.com/sigstore/sigstore-rs): the experimental
  implementation already has DSSE/in-toto verification code, despite broader
  README limitations. Its
  [verifier at `038e36ae`](https://github.com/sigstore/sigstore-rs/blob/038e36aefac21dd4ae608cda33736a494250fd1f/src/bundle/verify/verifier.rs)
  still has explicit TODOs for Merkle inclusion and signed entry timestamp
  verification. A successful bundle example does not establish policy parity.
- The separate [sigstore-rust](https://github.com/sigstore/sigstore-rust)
  project documents `sigstore-verify` 0.11, transparency proofs and TUF trust-root
  support. It is a candidate for C1, not a selected dependency. Check its
  released code, PyPI provenance conversion, exact publisher policy and negative
  vectors against the existing verifier. The first library's limitations do not
  prove that native verification is impossible. Source inspection and upstream
  claims are not an executed ai-stp verification result.

Out of scope: a Rust backend (#59), open-ended component kinds (#58), rewriting
public providers in their separate repositories, Corporate backend/policy work,
new credentials or access, and deleting rollback data. Existing exclusions for
real-agent qualification corpora, manual Windows/macOS acceptance by the agent
and scheduled production backups remain in the roadmap. CI platform evidence is
still required; unexecuted qualification must remain `not_verified`.
