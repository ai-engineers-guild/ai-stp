---
description: "Current ai_stp status and the ordered plan for remaining work."
last_verified: "2026-10-08"
---

# Current status and plan

This is the sole owner of the current plan. GitHub issues remain backlog, ADRs
record decisions, and specifications define requirements; review and session
plans are not continued literally after the implementation changes.
Earlier checkpoints, the session audits of September 24 and 26, and the
closing records are history in
[implementation-roadmap-history.md](../archive/implementation-roadmap-history.md):
true as of their dates, not a queue to replay.

## Current program: Rust CLI v2

The owner's October 8 instruction activates
[#57](https://github.com/ai-engineers-guild/ai-stp/issues/57), superseding its
earlier rewrite deferral. The objective is a complete native CLI with explicit
business scope, a small risk-based proof set and a controlled production switch.
Python CLI 0.0.43 remains the shipped engine. C0 froze migration evidence;
C1 establishes the isolated native preview under `apps/cli-v2`, without transferring
production state ownership. Its code-adjacent README owns the preview contract;
command details come from the executable registry, not copied specifications.

The [business scope and frozen ledger](cli-v2-scope.md) account for all 245
registered commands and nine intents at `7220c991`. They explain compatibility
risks, measured startup cost and the native provenance gap.
[ADR-0227](../adr/ADR-0227-rust-cli-v2-migration-boundary.md) owns isolation,
authority, state transfer and rollback. Existing implemented surfaces below
remain implemented; the following rows describe their Rust replacement.

| Checkpoint | Concrete result | Evidence required before advancing | State |
|---|---|---|---|
| C0 — scope and decisions | Complete command-to-business ledger, current behavior versus intended changes, architecture boundary and ordered migration plan | Verify every descriptor/handler/classification against the baseline revision; documentation gate, existing status contracts and final diff review | Recorded by [#717](https://github.com/ai-engineers-guild/ai-stp/issues/717); exact-SHA integration results belong to the issue/PR |
| C1 — native boundary proof | One Rust package with offline metadata, explicit schema-53 snapshot inspection, strict canonical data and native PEP 740 verification | Existing vectors and envelope/help consumers; all 51 tables from a real live-WAL backup; exact digest and newer-schema refusals; real PyPI artifact and eight negative mutations; three-OS CI and release-build measurements | Implemented; final integration and dated evidence tracked by [#718](https://github.com/ai-engineers-guild/ai-stp/issues/718) |
| C2 — useful read path | Explicit configuration and verified local passport/version reads, bounded project discovery/indexing, public catalog reads/cache and exact declared environment prerequisites | Shared consumer/canonical/Markdown vectors, real schema-53 snapshots/files/TCP, historical wire identity, refusal and cache bounds; actual API readback, three-OS CI and comparable release-build measurements | Implemented; integration and dated evidence tracked by [#734](https://github.com/ai-engineers-guild/ai-stp/issues/734) |
| C3 — authoring and selection | Rust adoption/scaffolding, immutable revisions/import/export, graph validation, mechanical eligibility and deterministic bundle compilation | Author → exact-version selection → bundle journey; canonical/descriptor/schema parity; refusal of invalid graphs, escaping paths, secrets and stale evidence | In progress in [#736](https://github.com/ai-engineers-guild/ai-stp/issues/736); the first native slice reads exact graphs, and the existing confirmation/cancellation race is corrected. Authoring writes and bundle completion remain pending |
| C4 — provider execution and recovery | Observed environment inspection, Rust trusted provider/software lifecycle, single- and multi-root installation, preserve/restore/switch and durable task flows for completed services | First one real provider on temporary targets, then all seven declared profiles; bounded process execution, interrupted apply, idempotent retry, rollback and active-environment handoff. Advertise only completed task intents | Planned |
| C5 — connected capabilities | Rust account/device/grants, private sync and conflict handling, publication/readback, technology mappings, assurance/reporting and existing governed-operation adapters | Real CLI↔API journeys, revocation/retry/restart, explicit visibility decisions, exact provenance and terminal readback; bounded heartbeat/usage delivery with current consent policy | Planned |
| C6 — native distribution and consumers | Owner-aware native install/update/recovery, attested artifacts/SBOM and a packaged Rust desktop sidecar | Exact-artifact Linux x86_64, Windows x86_64 and macOS arm64 execution; filtered desktop child environment, correct sidecar selection, installer coexistence, interruption/rollback and current-state recovery | Planned |
| C7 — controlled cutover and retirement | Transfer production writer ownership, switch the default executable, retire superseded Python CLI code/tests and reconcile all docs/memories | Every ledger row has a verified disposition; no unsupported pending task/state; tested quiescence/backup/ownership transfer; rollback after v2 mutations uses current compatible state or proved conversion; local/GitHub/deployed identities agree | Planned |

C2 separates declared requirements from executable environment observations:
`environment requirements` reads exact snapshot identities and variable names;
production `environment inspect` also invokes harness status and toolchain
preparation, so its observed-program completion is explicitly owned by C4.
C2 is a preview read path, not disposition of every production inspection leaf.
Project indexing intentionally refuses all symlinks, including internal aliases,
and catalog cache access requires an explicit isolated directory. Historical
public passports retain their original omitted fields and published digest.

### Checkpoint execution rules

Maintain only current code-adjacent contracts, generated command reference and
this ordered plan for v2. Do not copy the Python documentation/ADR tree into the
new package or add placeholder modules. C0's ledger is frozen migration evidence
until reconciliation at C7, not a second capability registry.

C1 verified the native signature dependency, but does not expose acquisition:
C4 must implement authenticated TUF refresh and apply the signed-environment
policy before installation. C5 must explicitly transfer credential ownership:
v1 uses service `ai-stp`, per-device `device-key.<device_id>`, shared
`cloud-credentials`/`pending-authorization`, and owner-only file fallback with
promotion side effects. C1 never opens that store. C6 must distinguish uv-tool,
pipx, dedicated-venv, shared/system and source ownership; the v1 updater journal
is keyed by interpreter prefix outside that prefix. A native preview must not
replace an installer-owned Python entry point or silently lose its journal.

1. Open a concrete checkpoint issue with owned paths and an exact starting SHA.
   Trace the affected current handlers, contract models and consumers before
   choosing a Rust API. Recheck primary upstream sources for the dependencies
   and failure boundary being changed; record what is observed and unresolved.
2. Resolve the business outcome first. For each changed ledger row, record
   `retain`, an evidenced replacement, or an evidenced retirement with consumer
   impact. Preserve exact pins, trust axes, provider authority, machine
   compatibility and recoverability; simplify internal structure freely.
3. Deliver small complete slices, with atomic commits and a draft PR into
   `dev`. Add only dependencies needed by that slice. Use a single package
   until a real boundary requires another. No placeholder handlers, fabricated
   success, automatic Python fallback or broad speculative abstraction.
4. Run the affected real-I/O/contract checks. Record failures as failures; fix
   or narrow the slice before promotion. A negative native feasibility result
   is useful evidence but does not complete C1 or authorize the final switch.
   Local isolated Rust work may continue while that dependency is resolved.
5. Rewrite affected active specs from the implemented behavior, regenerate
   owned artifacts, reconcile the command ledger and review the complete diff.
   Re-run current integration gates on the final SHA. Promote `dev` to `main`
   through the normal PR flow and synchronize local/remote history. Publish a
   preview/release only when its own artifact checks have actually passed.
6. After each wave, recheck working tree, remote refs, capability registry,
   state ownership, affected consumer behavior and relevant upstream guidance.
   Recheck production identity/health when promotion changes the deployed
   source. Update this plan and the checkpoint issue with the observed receipt.

The first code checkpoint must expose the hard native boundaries early rather
than spending the migration translating easy commands first. Full CLI scope
includes current Corporate client adapters; Corporate service implementation and
colleague policy remain outside this program. The backend rewrite (#59), an
extensible component-kind model (#58), and provider repository rewrites are not
implicitly activated by the Rust CLI decision.

## October 7–8 audit outcome

The audit started from `dev` at `ba8bcd0a` and production at `d9edaaf2`.
Implementation PR [#712](https://github.com/ai-engineers-guild/ai-stp/pull/712)
and promotion [#713](https://github.com/ai-engineers-guild/ai-stp/pull/713)
produced release commit `e7964854a6ff77200946b1c1462daeb245efb38f`.
The final publication-helper and documentation integration, branch synchronization
and deployed SHA are recorded in
[#711](https://github.com/ai-engineers-guild/ai-stp/issues/711).
Released artifacts stay bound to their original tags when later operational or
documentation commits are promoted. Revert an individual fix through the normal
PR flow; published versions, deployment records and database rollback copies
remain available.

| # | Work | Observed result |
|---|---|---|
| 1 | Desktop registry freshness and cancellation | Cache reads preserve the last verification timestamp; an expired failed probe refuses stale descriptors. Sign-in cancellation survives the browser-opening await. Local desktop checks and the three-OS promotion and release matrices pass. |
| 2 | Official download memory bound | The worker streams within the existing maximum and closes early refusals. Five transport regressions, backend checks and the deployed worker's normal publication path pass. |
| 3 | Official manifest curation | All 52 identities preserved: production reports 17 enabled and 35 paused with the exact reviewed manifest digest. Agent Browser job `33882` publishes `1.0` with 16 passed checks; public readback retains `component_verified: false` and the experimental trust line. Re-enabling conditions remain in the Official runbook. |
| 4 | Desktop sidecar cold start | Onedir resources use the Tauri resolver. Desktop 0.0.8 ships six bundles, all downloaded and verified against `SHA256SUMS`; the published deb's CLI also passes the filtered-environment runner probe. A controlled loaded-host comparison records 29% lower median wall time, not a portable latency promise. |
| 5 | Deferred dependency exit conditions | Primary release metadata checked October 7 still supports the five concrete deferrals in `dependency-policy.md`. Resume only when the documented upstream conditions change. |
| 6 | Release and live synchronization | CLI 0.0.43 is attested and byte-identical across candidate, GitHub and PyPI; Python 3.12/3.14 installation evidence passes. Local self-update is `verified`; all 13 doctor checks are ready with the existing user session's credential store. The release deployment readback at `e7964854` verified migration `0115` and all eight healthy containers. |
| 7 | Documentation and memory reconciliation | Closed Agent UX and dated roadmap checkpoints are archived. Active canon, deployment guidance and release evidence describe the implemented code. Project memory reconciliation preserves owner decisions and historical transcripts, with a private backup before replacement. |
| 8 | Publication dispatch identity | The helper requires the exact tagged candidate workflow and a successful attestation job, then binds approval to the dispatch response ID. Missing identities and approval HTTP failures are refusals. Eighteen focused regression/contract tests and backend static checks pass; final integration evidence is in #711. |

The published CLI's anonymous live slice agrees with the API and machine
projections for 204 components and 28 setups, and serves exact cached objects
when the route is unavailable. This is a dated catalog readback, not an invariant
object count. Login, grant and native-provider scenarios not driven in this audit
remain explicitly unverified; earlier receipts do not qualify them on a new SHA.

### Verification and stop conditions

For rows 1 and 4, use `just desktop-check`, the real bundled-sidecar probe and
the three-OS desktop workflow. For rows 2 and 3, use focused shared-source and
Official tests, PostgreSQL integration tests, `just back-static`, and the
backend gate. `just docs-check` proves document and generated-index changes;
the complete `check` workflow proves the integration and promotion heads.
Process-terminating local tests run in an isolated PID namespace. Python gate
commands share one environment and are run sequentially to avoid dependency
installation races.

After each wave, fetch remote refs, review the exact diff, check the affected
invariants, revisit the relevant upstream guidance and record actual results.
A new finding joins this table only after reproduction against code. A failed
compatibility or security check is a refusal, never a reason to weaken the
check or label incomplete evidence as passed.

Primary references checked during this audit:

- [HTTPX streaming responses](https://www.python-httpx.org/async/#streaming-responses):
  consume bounded chunks inside a response context so early exit closes it.
- [GitHub REST best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api):
  honor retry/reset headers and avoid concurrent requests that increase secondary limits.
- [PyInstaller operating modes](https://pyinstaller.org/en/stable/operating-mode.html)
  and [Tauri resources](https://v2.tauri.app/develop/resources/): package the whole
  frozen directory and resolve it through the platform resource directory.

These are established implementation practices. Pages were read on October 7;
their live contents are not represented as a historical September 26 snapshot.

### Audit coverage and closed uncertainties

The local stores contain three Devin sessions active in the ten-day window,
two Claude Code sessions, and this Codex session. The September 26 Codex and
Devin sessions are supplementary context. Cursor's latest project session is
September 19; Grok's is September 20, so neither has local activity in the
window. Session text is a source of candidates, not an instruction to replay
old plans. Only available local history is claimed; remote-only or deleted
sessions cannot be reconstructed from it. Raw transcripts and personal data remain
outside the repository.

The October 6 and 7 daily runs resolve the worker-token uncertainty: all 52
attempts reach a terminal domain result; no new rate-limit dead letter appears.
October 7 completes by 01:34 UTC. The remaining 36 refusals belong to curation,
not to an unproven need for new credentials. Telemetry retention succeeds on
both days. At the baseline, every production container is healthy, the timer
is active, disk usage is 49%, and the API SHA matches `main` and `deploy/prod`.

### External prerequisites retained

- PostgreSQL 16 volume `ai_stp_pgdata` remains a rollback copy; removal requires
  an owner decision and is not a stabilization task.
- Desktop code signing remains conditional on certificates and a distribution
  requirement; the unsigned release limitation stays explicit.
- The Windows process-contract flake is observed through CI. Its improved
  exit-code/stderr diagnostics must identify a recurrence before a speculative
  platform change is made.

Not pursued by owner decision: real-agent qualification corpora (GPT OSS 120B
through agy-cli, Claude haiku), native Windows and macOS acceptance runs by an
agent, and scheduled production backups (SPEC-024 `REQ-2409`). Outside this
plan's owner: the Corporate Hub and `[Enterprise]` backlog (#224, #541–#544
and the issues it links) and setup-systems #316.

## Decision-making vision

- Seven setup systems own native harness writes and real software
  install/update/remove; `ai-stp` invokes the same lifecycle mechanically.
- Existing configuration becomes managed only through explicit adoption with an
  exact plan, never through silent ownership.
- The current component vocabulary is the closed `component_type` list in
  `docs/contracts/component-setup-passports.md` and may be extended by a new
  ADR when a proven native form exists.
- The platform vocabulary covers Linux, Windows, and macOS and
  `x86_64`/`arm64`. ADR-0172 requires beta qualification on Linux x86_64,
  Windows x86_64 and macOS arm64; the other three pairs remain `not_verified`
  and do not delay beta. Native binaries are specific to their platform.
- Package classifiers do not prove qualification. Evidence binds the exact
  candidate artifacts; a Python-version install matrix and provider native
  qualification answer different questions. Older passing matrices do not
  qualify a new candidate, and the owner exclusions above remain explicit.
- The agent chooses the engineering path within the task. Digest, rollback,
  provenance, and compatibility remain mechanical integrity constraints without
  creating an additional approval round.

## Implemented surfaces

| Area | Observable state |
|---|---|
| Local-first CLI | SQLite registry, passports/revisions, discovery/adoption, selection, bundle, install/status/diff/update/rollback/recovery, machine help, and canonical Skill |
| Platform | `/v1`, PostgreSQL, object storage, queue, authentication/devices, sync, publication, grants/reports, public catalog, article, and SEO projections |
| Web | Landing, catalog/detail, account/device/owner surfaces, content hub, machine projections, and a three-OS test matrix |
| Providers | Seven public setup systems at `0.0.88`, read through the vendored provider kit `0.2.15` and protocol v3: native configuration, backup/recovery and software lifecycle. Launch completeness per provider is measured evidence, not a property of the release. |
| Release | `ai-stp-cli==0.0.43` on PyPI with its GitHub Release (SBOM, manifest, `SHA256SUMS`). Automatic provider acquisition uses PyPI with the CLI-managed verifier (`ADR-0171`); explicit GitHub acquisition retains its attestation policy. Self-update of the CLI wheel is `SPEC-072` / `ADR-0170`. Source integration, package publication and installed PATH identity are separate observations. |
| Desktop | `ai-stp-desktop` 0.0.8: a Tauri 2 shell over the CLI machine contract with a frozen CLI sidecar (`ADR-0222`); deb, rpm and AppImage for Linux, an aarch64 dmg, and an exe and msi for Windows, unsigned. |
| Catalog | The canonical first-party corpus models seven harness families and four postures. Identity projection, exact target assurance, and normal-path publication/readback evidence are implemented in the current platform closeout for `#146`/`#155`. |
| OBT support tiers | All seven harnesses are `beta` (`SUPPORT_TIERS`, `SPEC-033` REQ-3315). `primary` remains a valid later GA label with no current members |

## Working practice

1. Any handler that reads a hidden `confirm` must break the registry-parity test.
2. A local reversible operation uses the exact expected value as confirmation; a
   new boolean must not reintroduce a resolved engineering decision as a human
   stop. Apply the current task-authority policy (`ADR-0150`).
3. Do not copy old plans or reviews into active documentation. A new session
   reads this roadmap, the specifications and machine help, then checks them
   against the current bytes.
4. Every evidence script has a recipe that names it. A script nobody can invoke
   is not a check; `verify_contribution_slice` sat unreferenced for a day and its
   first real run found three defects in itself.

## Architecture-alignment dispositions

An older architecture-alignment audit named workstreams that later ADRs already
closed or forbade. Those findings are not re-opened here:

| Finding | Disposition |
|---|---|
| Protect `ai-stp/main` (GOV-001) | ADR-0180 restores protected `main`, promotion checks, and administrator bypass with zero mandatory approvals (default later moved to `main`; see the ADR amendment). |
| Six-package publication (REL-002) | Superseded by `ADR-0146`: one public `ai-stp-cli` wheel. Historical six-package artifacts stay immutable. |
| Provider-owned multi-root commit (LAY-002) | Superseded by `ADR-0145` / SPEC-058: the consumer owns a recoverable transaction over unchanged provider v3 (one target). |
| PyPI as the default provider channel (PYP-002) | Implemented by `ADR-0171`: automatic acquisition uses PyPI with a CLI-owned verifier; GitHub is explicit. Three primary platform pairs are required; the other three remain `not_verified`. Current default selection does not qualify an unexercised platform. |
| Public provider disclosure (PUB-001/002) | Owned by the provider estate, not this consumer. Public documentation remains self-contained. |
| Persist adaptation assessments (CMP-003) | Implemented by the target-bound assessment history/latest model and migration `0050`; PostgreSQL concurrency evidence is required at release time. |
| Catalog/web per-harness matrix (CMP-004) | Implemented by exact adaptation target matrices and exact-only harness filters; aggregate fields remain compatibility-only. |
| Scaffold v5 (SCA-001) | Historical milestone, superseded by the `/6` writer below: `source/AGENTS.md` canon, generated `projections/<harness>/` in the native layout, no speculative adaptation document, no invented passport tags, and one reported Git root. |
| Portable hook handler (`#116`) | Done: `component-scaffold/6` writes the derived closed-set manifest and runnable handler under `source/` for portable hooks; `/5` remains validatable. `setup-scaffold/5` embeds `/6`. |
| Authoring freeze (SCA-004) | Done: `setup-scaffold/5` points nested members at `projections/<harness>` with `managed_paths`; compose and `component version release` refuse `TODO(ai-stp-scaffold):` markers and freeze a content-addressed `ComponentAdaptation` on the exact provider surface. |
| Setup export (SCA-003) | Done: `setup export` writes a separate `ai-stp-setup-export/1` review tree whose manifest binds the recorded passport, definition, and every exported file; it mutates neither authoring nor harness state. |
| Control-plane Skill package (`#97`) | Done: `skill install` writes `SKILL.md` plus `references/` for every harness; projections carry the procedure; Russian is a generated locale; machine help still owns flags (`ADR-0149`). |
| Rust CLI rewrite | Activated by the October 8 owner instruction and ADR-0227; the C0–C7 program above replaces the earlier deferral. Python remains the production engine until the controlled cutover. |
| Further component kinds | Separate backlog. The ninth `cli` kind already exists under `ADR-0155`; its existence does not prove runtime lifecycle completion. Historical experiments are not current evidence. |

## Explicitly out of scope for this pass

Corporate backend implementation and its proposals remain owned by the colleague's
workstream; existing CLI adapters are retained in the Rust compatibility scope.
GitLab integration and SAML sign-in already ship in production;
they are not unimplemented backlog. New product scope is evaluated
against current code and requires the applicable specification and ADR.

## Done

Work is complete when current public/private bytes are synchronized, the required
three-platform evidence is executed on exact releases, live slices refer to the
deployed SHA, documentation is generated from its owners, and the final diff and
Git state are clean. `not_verified` is an honest remaining result, not a reason
to add a manual approval or hide a matrix row.
