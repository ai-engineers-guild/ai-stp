---
description: "Current ai_stp status and the ordered plan for remaining work."
last_verified: "2026-09-24"
---

# Current status and plan

This is the sole owner of the current plan. GitHub issues remain backlog, ADRs
record decisions, and specifications define requirements; review and session
plans are not continued literally after the implementation changes.

The remaining-work owner tracks current `main`. Recast file identity, modes,
scopes, and native MCP/agent/hook/plugin transforms landed in `#145` / `#147` /
`#151` (transform `1.3`). Shared `cli` prefix containment landed in `#152`.
The `#146`/`#155` platform closeout is implemented in this tree; GitHub issue
state remains a separate maintainer action. Merged PRs are not the OBT release.

## Session audit and execution plan — 2026-09-24

This checkpoint supersedes the dated execution orders below. Baseline:
`dev` commit `b9555283fec772996b09d6243ec84a7d5b5eedbb`, tree
`3f0594cf580727b644fc4ae4dd1b62a8d8cc5e66`; `main` and the live API report
`0bc51644a2de42ea2e8b7b5770d8f747770f5c52`. The working tree was clean.
The heartbeat change in #404 is integrated into `dev`, not yet promoted.
Work proceeds on `fix/session-audit-closeout`, created from that `dev`.

### Session coverage and interpretation

Local project records were inspected read-only: four Cursor transcripts
(two principal sessions and two historical investigations), three Claude Code
records (one substantive conversation, one local-command record, one without
conversation), nine Grok conversations (including historical child sessions),
and two Devin conversations. Codex contains the current project session;
no earlier project-specific Codex rollout was found in the available store.
Cursor also retains one empty CLI session. Cloud-only, removed, and older
unsynchronized histories cannot be certified from these local records.
Six additional Claude qualification replay records were compared with their
retained CLI logs. The failing `unsupported-project-local:4` cell used `.`
instead of the requested `relative`, matching the stored failure. A Cursor
host-recovery conversation mentions this project but contains no additional
project implementation task.

The local audit inventory digest is
`sha256:90a7906ec4f9d36223274c0e35eeea8756470243ee5ee264780df16864091cb4`.
Raw conversations, tool output, credentials, and personal data are not copied
into this repository. Historical promises are leads to check, not authority
to reinstate superseded behavior.

| Historical lead | Current code or evidence | Disposition |
| --- | --- | --- |
| Cursor: one-intent kernel, missing stdin, missing control attachment, failed #297 | `application/task.py`, `application/initialize.py`, `app.py`, `test_cli_task_driver.py`; eight shipped intents and merged #297 | Implemented; retain regressions, do not rebuild the kernel |
| Claude: sync-plan digest disagreement and receipt loss | `tests/unit/test_cli_project_sync_apply.py`, `tests/unit/test_cli_project_revision.py`, project sync and revision services; #255–#277 | Repairs shipped; live two-device evidence remains distinct |
| Grok: classify the canon, archive stale plans, replace fake CLI/API journeys | `implementation-canon.md`, `docs/archive/`, `tests/api/cli/`, `tests/support/postgres.py` | Implemented by surface; no arbitrary document-count target or mass deletion |
| Devin: just/Docker/Rust provider standards | `standards/just.md`, `standards/docker.md`, `standards/setup-systems.md` | Present; provider-source changes belong to their own repository |
| Devin: selector errors, parse failures, machine parameter rules | `errors.py`, `app.py`, registry declarations, release `0.0.28` | Shipped; current registry includes subsequent corporate commands |
| Repeated claim that PostgreSQL cannot run on this workstation | Docker and a local PostgreSQL 16 image are available | Obsolete environment claim; run real isolated database tests |
| Agent UX checkpoint says 53/100; later text says 100/100 | Retained Haiku overlay: 99 pass, 1 fail; GPT-OSS overlay: 89 pass, 11 unrun | Correct dated records; neither overlay qualifies the current candidate |

Paths in the table are relative to their owning CLI application or test tree
where shortened. The audit covers CLI, contracts, API/platform/worker, web,
generated artifacts, deployment state and their checks. Corporate code is
included in regression execution; colleague specifications, ADRs and issue
ownership remain unchanged.

### Verified defects and ordered work

The plan was checked a second time against actual functions and temporary-file
reproductions before implementation. That review added A3: two distinct file
trees currently produce the same qualification digest without a SHA-256
collision. It also expanded A2 to native/isolation writers and invalidation,
which can relabel existing model results even without running another model.
The release-ledger review then reproduced A3b: the artifact validator skipped
a second conflicting digest for the same filename, while duplicate provider
repositories with different source commits could still produce `complete`.
This extends the evidence-identity repair before final integration.

| Order | Work and code owner | Acceptance and dependencies |
| --- | --- | --- |
| A1 | Preserve measured model identity in `application/qualify.py:report` | A Haiku overlay reports Haiku, not the GPT-OSS default; absent identity is not invented for measured cells |
| A2 | Keep each scored overlay bound to one model in `agy_qualify.py` | Reject mixed-model scoring/fill before workspace or model effects; native/isolation updates and invalidation preserve existing attribution; rejection preserves original bytes; same-model replay is idempotent |
| A3 | Unambiguously frame `application/qualify.py:tree_digest` | A one-file payload containing another entry's delimiters cannot equal the digest of a two-file tree; rename/content changes change identity; traversal order does not; retain old measurements as historical |
| A3b | Reject contradictory estate identities in `ai_stp_contracts.estate_release` | One provider repository appears once; a filename cannot claim different digests across consumer distributions, native artifacts or provider wheels; real-file validator regressions refuse the contradictory records before a complete verdict |
| A4 | Reconcile this roadmap, Agent UX checkpoint and sync specifications with source and retained evidence | One current checkpoint, explicit model/date/limits, no stale next-release instruction, no unsupported native or release pass. SPEC-009 REQ-912 and SPEC-005 incorrectly promised automatic version reissue; `sync_versions.receive`, `versions.record` and the collision rollback regression implement typed refusal with unchanged local data and cursor. Describe that shipped behavior without inventing automatic recovery |
| A5 | Verify actual services and full gate | `just docs-check`, `just back-static`, `just back-test` with disposable PostgreSQL, `just web-check`, plus resource/build/install regression and security recipes; explain each environment skip; use pinned Bun without changing the user's installation; dispatch existing platform/configuration/software evidence workflows on the work SHA after verifying seven exact provider tags |
| A5b | Repair the live sync collision fixture in `release_scripts/verify_sync_slice.py` | The authenticated run reproduced a release refusal: adoption alone omits required declared metadata. Reuse the evidence helper and prove the fixture releases through real CLI commands. A repeat also reused the previous divergent probe; give each run a separate native path and prove adoption does not reopen the previous object. Seed the native source through adoption on both devices: passport sync does not transfer the source bytes required for each offline release. Preserve earlier fixtures, then repeat all five live scenarios with two isolated authenticated homes; do not weaken release or conflict validation |
| A5c | Verify effects in the live sync verdict | The replay receipt may count previously processed events, so receipt acceptance alone does not prove absence of duplicates. Require equal device heads after fast-forward, an empty peer pull with unchanged cursor after replay, and an accepted receipt after the merged push; regression fixtures must reject each false-positive case |
| A5d | Stop boolean ancestry lookup once the ancestor is found in `local/revisions.py:is_ancestor` | The 10,000-revision measurement performed 10,002 SQL statements for an immediate parent. Bound that case independently of history length; retain correct self, unknown, unrelated and multi-parent results and read-only behavior. Keep deterministic `common_ancestor` selection unchanged; remeasure the retained database |
| A5e | Isolate the unchanged-device rescan regression from workstation version probes in `test_cli_commands.py` | The full local run exposed a test assumption: repeated live OpenCode probes changed from a reported version to `unknown`, which correctly creates a revision. Retained repeat snapshots reproduce that transition. Supply deterministic detector observations; unchanged known or unknown versions retain the revision despite a later observation time, while version changes and transitions to or from `unknown` create one child revision. Keep real detector subprocess coverage and runtime timeouts unchanged |
| A5f | Reconcile deployment guidance with the public workflow and host pull script before promotion | The active runbook still claims this tree has no deployment workflow, names a withheld private test, calls production staging, and describes a deploy key and runner on the host. Check `deploy.yml`, `pull-deploy.sh`, `mark-transfer.sh` and public deployment tests; correct the runbook and stale workflow commentary while preserving executable workflow content |
| A5g | Isolate the same-key task race from cold schema preparation in `test_cli_task.py` | The `a33549ab` dev-push Windows run exceeded the test's ten-second future wait, while the same-head PR suite passed. A temporary eleven-second first-migration delay reproduces that timeout locally. Prepare the real registry before starting both competing tasks, retaining their ten-second waits and result assertions; the dedicated concurrent-first-open registry regression still covers migrations. Repeat the delayed experiment, both concurrency regressions and the exact-head gate |
| A5h | Repair task-start diagnostics exposed by interactive Antigravity | A fresh native Herdr/agy GPT OSS 120B session repeatedly used positional intents and a short idempotency key. Name the required intent option, publish the existing key constraint in machine help, and return the shared pattern plus scoped repair help without echoing invalid values. Retain rejection before task creation, idempotent boundary keys, original failed attempts and separate model-report errors. Repeat the actual user journeys against the installed repaired wheel |
| A5i | Preserve authored component files in native projections | The same interactive session authored a skill with a Python script and reproduced an internal source error. Map every source file to its native path, retaining nested files and omitting generated notes; reject ambiguous single-file surfaces and invalid names with validation errors. Check archive bytes and replay, then repeat author, change and fresh native loading through Herdr/agy. Model claims about restored files remain unverified until actual files and commands agree |
| A6 | Review, integrate and verify | Explicit-path staging, exact-SHA PR into `dev`, promotion into `main` after checks, served-SHA readback, synchronize permanent local branches; a green historical SHA is not the final gate |

A1–A3b change qualification evidence handling, not provider ownership or task
architecture. Update SPEC-080 REQ-8020 and SPEC-061 from the implemented regression tests;
no new architecture rule or dependency is needed. Regenerate affected sources
and indexes through their owners. Before each remote mutation, re-read the
source/head SHA and PR state. Re-running scoring with the same model/key must
not duplicate a cell. Rollback is a revert of the work merge; keep all older
evidence files and do not rewrite published artifacts or tags.

Observed during this audit: baseline `just docs-check` and `just back-static`
passed; `just security` reported no vulnerabilities in 1,013 web dependencies.
The real RustFS owner/bucket-isolation test passed against a separate disposable
container. `just evidence-live` passed anonymously against `0bc51644`, listing
187 components and 28 setups and checking exact-version, machine-projection
and offline-cache parity. Its login/revocation scenarios remain `not_verified`.
The initial web command correctly refused installed Bun 1.4.2; subsequent web
checks use the repository pin 1.4.0 from a temporary tool directory.
Full-suite and final-SHA results belong to the work PR, not this baseline.

The user-directed workstation run installed the `f64befa0` CLI wheel into an
isolated environment and staged all seven attested provider `0.0.73` binaries.
The existing user binaries were retained. Through Herdr, `agy` ran
`gpt-oss-120b-medium` against all 20 scenarios: 19 passed and the initial
initialization attempt failed after repeated commands, stale revisions and an
invented command. Four independent initialization repetitions passed; the
original failure remains. The resulting overlay is 23 pass / 1 fail, with
76 qualification cells unrun, not a completed 100-cell qualification.
Its digest is `sha256:c5cb4c704c1931d116ac5187ebb9d445c263fec43f1a7e68ea0abe6c3ffc2c76`.
Bubblewrap isolation was enforced, including IPv4, IPv6 and DNS controls.

The exact `f64befa0` CI gate passed all 40 checks. Native platform evidence
passed all four Python/platform legs; configuration and software evidence each
passed 21/21 required harness/platform rows. Local provider evidence verified
seven global and nine additional scoped profiles with no projection
disagreements, contribution evidence passed four cases, and all 47 cited
sources were reachable. These measurements are bound to that candidate, not
silently relabeled as a later commit. The final source gate and integration
record belong to [PR #406](https://github.com/ai-engineers-guild/ai-stp/pull/406).

Authenticated owner/publication read and preview evidence passed nine checks;
publication, invitations and moderation submissions were not driven. The sync
fixture repairs and stricter verdict are covered by 40 local sync tests.
The final authenticated live run verified all five scenarios: equal heads after
fast-forward, no new events or cursor movement on replay, conflict refusal,
an accepted merged push, and immutable collision refusal preserving the local
release. The intentionally conflicting devices and their evidence are retained.
The full local backend run was interrupted at 89% with signal 15 and has no
passing verdict; the exact-head CI suite is the complete backend evidence.
Local web tests passed 749 main and 130 catalog cases after a loaded-host
timeout run; browser regression passed 224 with ten declared skips. No timeout
or assertion was relaxed. Ancestry measurement on 10,000 revisions observed
10,002 SQL statements even for the immediate parent (about 0.30 s on this
shared host); it is retained for #256, not treated as a performance guarantee.
The bounded lookup repair reduces that immediate-parent case to two SQL
statements at 100, 1,000 and 10,000 revisions (about 0.0002 s at 10,000 in the
repeat). A distant root still requires a full traversal. A real-registry
regression bounds the query count and checks that reads do not alter the
database; branching and unknown-revision cases retain their verdicts.

A later complete local run on `9eaf3964` finished with 7,853 passed, one failed
and 100 conditional skips (87.40% coverage). The unchanged-device rescan test
assumed that real workstation probes always return the same answer. An
instrumented repetition reproduced four failures in twelve attempts: OpenCode
and Cursor version observations changed to or from `unknown`. Creating a child
revision for those changed facts is correct. A5e makes that regression's inputs
deterministic and checks both stable observations and changed versions, without
changing detection deadlines or runtime behavior. Final checks after this test
repair remain owned by the work PR.

The exact installed `9eaf3964` wheel also passed all 20 first-pass GPT OSS
scenarios through Herdr/agy, including the three earlier control scenarios.
The expanded overlay digest is
`sha256:deb37cbc3c1f4e7e274e338ce5b1c6767e832439bd4f44e2a9690d7f94496293`.
It is separate from the earlier `f64befa0` 23/24 sample and leaves 80 of the
100 qualification cells unrun; neither the initial failure nor that remaining
qualification work is erased.

### Remainders that this audit must not erase

| Remainder | Next concrete proof or owner |
| --- | --- |
| Agent UX #261–#275 and setup-systems #316 | Retain implementation evidence per child issue; native Windows x86_64/macOS arm64 and fresh-session loading must be measured against exact candidate/provider bytes before epic closure |
| Full-beta 28 setups × 3 required platforms | Follow SPEC-061 and ADR-0172, including retained evidence files and artifact binding; Linux arm64, Windows arm64 and macOS x86_64 remain optional, not release blockers |
| Account/private publication/grants/two-device journeys | Use isolated authenticated devices and explicit test objects; anonymous health and local API tests do not prove these live journeys |
| #256 estate ledger, ancestry performance and promotion policy | Existing owner; keep the issue open and its missing measurements visible; do not narrow deployment checks to make an audit green |
| #358 standalone corporate component assignments and other corporate backlog | Colleague scope; do not equate task-based component installation with corporate assignment verification |
| Old PyPI internal-project cleanup (#100) | Recheck existence; deletion has no recovery path and is not part of reversible code repair |
| Rust rewrites, new component kinds, new integrations | Backlog proposals, not defects inferred from old session requests |

Completion of A1–A6 is a code-audit closeout. It is not completion of the full
beta or proof that every possible defect has been found. Evidence gaps remain
named until their own acceptance runs exist.

## Previous checkpoint — 2026-09-20

Tracked line: GitHub `main` promotes to `deploy/prod`; the host timer pulls
that ref. Production identity is `GET https://ai-stp.aiguild.space/v1/system/version`
(`git_commit`). User docs are `https://docs.nddev.asia`. API package version
and CLI version are independent; do not treat `0.0.16` on the API as a CLI
drift.

On `main` now, and not in the September 8 snapshot below:

- Agent-first CLI: eight drained intents ([#297](https://github.com/ai-engineers-guild/ai-stp/pull/297)); `ai-stp-cli` `0.0.28` on PyPI ([#386](https://github.com/ai-engineers-guild/ai-stp/pull/386) / [#387](https://github.com/ai-engineers-guild/ai-stp/pull/387))
- Local technology detection, review, and scan publication ([#366](https://github.com/ai-engineers-guild/ai-stp/pull/366)); `--project`/`--root` declared `exactly_one` in machine help ([#367](https://github.com/ai-engineers-guild/ai-stp/pull/367)); Haiku 4.5 agent qualification recorded ([#368](https://github.com/ai-engineers-guild/ai-stp/pull/368))
- Machine-help contract audit: `install plan` source XOR conditional on `action` (`REQ-1207`), and eight handler-enforced rules declared (`select graph`, `select propose`, `select impact-report`, `component adaptation add`, `component materialize plan|apply`, `component portability plan|apply`) ([#375](https://github.com/ai-engineers-guild/ai-stp/pull/375)); `at_most_one`/`forbidden_when` kinds close the sourceless-action declarations on `install plan` ([#380](https://github.com/ai-engineers-guild/ai-stp/pull/380))
- Parse-failure contract: declared leaves list every missing required option in `error.details.options` and correct to their own `help --path`; `--version` corrects to `version`; continuations join the full path; `--` marks operand text ([#385](https://github.com/ai-engineers-guild/ai-stp/pull/385))
- `branch-policy.yml` SC2015 ([#304](https://github.com/ai-engineers-guild/ai-stp/pull/304))
- `standards/just.md` and `standards/docker.md` ([#306](https://github.com/ai-engineers-guild/ai-stp/pull/306)–[#308](https://github.com/ai-engineers-guild/ai-stp/pull/308)); `infra-*` is outside `just check`
- Deploy secret preflight, least-privilege compose env, docs origin probe ([#309](https://github.com/ai-engineers-guild/ai-stp/pull/309) / [#311](https://github.com/ai-engineers-guild/ai-stp/pull/311))
- Host `.env.prod` must name `AI_STP_STORAGE_ARTIFACT_BUCKET` and `AI_STP_STORAGE_ASSET_BUCKET` (they may equal the existing `AI_STP_STORAGE_BUCKET` during upgrade)
- Consumer kit in this tree is `0.2.13`. Public `NDDev-OpenNetwork/*-setup-system` tags are `0.0.73` and vendor that kit
- Observed live 2026-09-20: `GET /v1/system/version` `git_commit` matched `origin/main` and `origin/deploy/prod` (`34dde4bb`); API package `0.0.16`; `/v1/health/ready` 200; `https://docs.nddev.asia` 200
- Observed live 2026-09-22: `GET /v1/system/version` `git_commit` `6f9ef8f5` matches `origin/main` and `origin/deploy/prod` (tag `v0.0.24`); API package `0.0.16`; `/v1/health/live` and `/v1/health/ready` 200
- Observed live 2026-09-22 (later): `origin/main` and `origin/deploy/prod` at `60aec921` (tag `v0.0.25`); PyPI `ai-stp-cli` latest `0.0.25`; host `git_commit` follows the deploy/prod pull interval

Still open on this owner's line: Agent UX epic [#261](https://github.com/ai-engineers-guild/ai-stp/issues/261)–#275 (Haiku qualify, native win/mac), setup-systems #316. Corporate / `feat/milestone-6-b2b-03` is a colleague scope — do not close those issues from this plan.

The September 8 table below is a historical snapshot. Its CLI `0.0.21` and
production SHA are not current.

## Active full-beta execution — September 8 (historical)

The user selected seven harnesses on three required platforms: Linux x86_64,
Windows x86_64 and macOS arm64. Linux arm64, Windows arm64 and macOS x86_64
are explicitly not_verified and do not delay this beta. One agent owns implementation and integration across CLI,
contracts, API/platform/worker/web/deployment and the source setup systems. No
subagents or new worktrees are used. The installed `ai-stp-cli` is the user's
entry point for acquisition, installation, updates and recovery.

Baseline when post-broadcast work resumed: main and production `b2e99a5e`,
CLI `0.0.21` on PyPI and in the user's PATH, providers `0.0.69`. The release
candidate and registry readback agreed byte-for-byte; the user's registry was
preserved. API rate limits remain unchanged by the owner's decision. The
post-broadcast task resumes implementation; it does not reopen completed release
work or treat the interrupted explicit model run as a passed scenario.

| Stage | Outcome and remaining work | State |
|---|---|---|
| R1 | Complete EN/RU Skill packages and usable agent procedure | Installed package released; real agy-driven Codex minimal installation passed. Standalone repository reference closure merged in #194; 49 package/probe tests passed |
| R2 | Private metadata, visibility and immutable publication | Draft promotion and setup ownership merged in #193. Legacy component identity repair is #195; remaining live private/grant journeys belong to R6 |
| R3 | Deployment progression and recovery | Green main checks promote production normally; do not infer deployed SHA from a merge. Broader restore evidence remains open |
| R4 | Owning-installer update/recovery and managed PyPI provider bootstrap | Released; GitHub/PyPI apply revalidation passed. Schema-aware rollback is implemented; 43 focused tests and a real isolated uv update/compatible rollback/incompatible refusal passed on Linux. The new reader release remains pending |
| R5 | Seven providers and all four setup variants | Providers released; native program and configuration lifecycle passed on the three required platforms; full variant content/invocation evidence remains open |
| R6 | Corpus and account journeys | All 106 objects published. Snapshot closure/recovery merged in #192; a repeated main-source read on two copied devices reached up_to_date with no pending versions. Collision reconciliation, full artifact readback and remaining live account journeys are open |
| R7 | Complete 28-setup by 3-platform qualification | Basic 21 provider/configuration cells passed; full 84 setup/platform cells and shared candidate binding remain open |
| R8 | Final release evidence | CLI 0.0.21 release/PATH/production verified; file-bound estate completeness remains open |

Immediate execution order: finish integration of the current fixes and publish
the next verified CLI reader;
then implement immutable offline-version collision reconciliation, finish live
account/publication and artifact readback, and qualify the full variant/native
matrix against one candidate. Bind estate verdicts to retained artifact/evidence
files before the coordinated full-beta release. A previous CLI cannot read schema
35 merely because its wheel was restored; rewinding user data is not an implicit
rollback step.

The post-broadcast publication repair promotes an existing owned draft through
the validated materialization path and preserves published lifecycle/visibility
on replay. Setup ownership is checked across versions in the API and worker;
concurrent first catalog writes establish one owner. The affected PostgreSQL,
API and publication regression suite passed 78 tests. These repairs do not
replace the remaining live publication/grant evidence.

The legacy identity follow-up passed 973 platform/API/integration tests with
one skip. Database doubles were replaced by PostgreSQL commit/rollback and
idempotency tests. Diagnostics now treats supported automatic migration as
ready while remaining read-only; 98 CLI/registry tests passed. These source
fixes are not yet in the user's installed 0.0.21 wheel.

Confirmed repairs include mismatched private wire models, missing visibility
routes, artifact resealing of an existing X.Y, unchecked projection bind answers,
updater false rollback success and interrupted-update reconciliation. The estate
validator must bind actual artifact/evidence files; matrix labels alone are not
qualification. Native consumer workflows must consume the same candidate wheel.

Fast iterations run affected checks; final qualification covers the full selected
matrix and the repository gates. Technical reader releases may satisfy rollout
ordering but do not finish the beta. Version numbers remain independent across
CLI, API, providers, kit and immutable objects.

## September 7 audit and execution order

The initial measurement started at `44116426`, after reviewing September 4–7
GitHub history and available Claude, Codex and Grok session handoffs. The table
below preserves that baseline; the execution results following it are current.
Session closure and a green source check do not establish a healthy deployed product.

| Recent work | Current evidence and limitation |
|---|---|
| Discovery, adoption and exact identity | `#119`, `#120`, `#129`, `#130`, `#135`, `#159`, `#170`: bounded discovery, root overlap refusal, moved-source identity, program/materialization identity, and MCP host-key freezing. Preserve their regressions. |
| Authoring and composition | `#113`, `#123`, `#124`, `#142`, `#144`, `#145`, `#147`, `#151`, `#156`: coordinated standard family, native adaptations, recast, scoped conversion and separate component evaluation. These are source implementations, not a new release qualification. |
| Authority and harness coverage | `#131`–`#138`, `#141`, `#153`: task authority, uniform preset autonomy, seven beta harnesses, and explicit bootstrap roots. |
| Distribution | `#160` / `#161`: published CLI `0.0.18`; seven provider releases `0.0.66` are recorded by their public repositories. The MCP fix in `#170` postdates the CLI artifact. |
| Platform and web | The current open issues `#139`, `#140`, `#146`, `#155`, `#162`–`#169` retain specific consumer and user-flow gaps. The unmerged colleague branch must be compared before duplicating its implementation. |
| Production | `/v1/system/version` returned `0.0.16`, commit `aa9314ff`, schema `0036_official_projection`. The latest deploy run `34068205176` failed while expecting schema `0047_repair_official_locale_collisions`. Host logs reproduce an account identity collision in migration `0040`. |

Current execution results on September 7:

- Deployment recovery is complete: `#171` repairs account-handle collisions;
  normal main checks and public deployment have passed. The public origin serves
  `9ed36dae`, schema `0052`; API package `0.0.16` is independent of CLI versioning.
- Provider authoring is complete for `0.0.67`: seven native builder collections,
  refreshed vendor pins, read-only generator checking, exact public renders,
  release artifacts and released-consumer conformance are verified.
- Canonical ingestion, `cli` storage taxonomy and derived beta support landed
  before the combined platform/web integration. `#173` and `#174` are included
  in `#175`, together with setup presentation, catalog navigation, avatar/logging
  and context-budget repairs. `#175` passed all PR checks and deployed normally.
- Additional complete-identity/freshness assessment repairs merged in `#176`
  (`96bb1ca8`) after the full backend gate and all PR checks. They resolve real
  PostgreSQL failures and validation/read/search disagreement after expiry.
  Migration `0053` passed twice on a restored production snapshot; its normal
  main-check/deployment progression remains a separate result.
- The corpus in this change is captured from attested `0.0.67` releases. Two
  captures agree and preserve all identities; native graph/placement tests pass.
  Normal-path publication still requires a current owner session. Browser policy
  verification failure currently prevents completing that login through automation.
- Private owner/grantee storage and source closure (`#162`–`#164`), final CLI
  candidate publication, and current G5 launch cells remain open.

Continue in the original dependency order:

1. **Restore deployment progression.** Reproduce the unnamed-account collision
   against an isolated database upgraded from the deployed schema. Preserve
   the complete account identifier when deriving its default handle, keep
   existing names and ownership intact, and prove repeat upgrade and rollback.
   Deploy through the normal promoted ref and verify the served commit/schema.
2. **Complete native setup authoring.** The provider builders must create a
   complete tool collection for user tasks, document supplied capabilities,
   resolve exact components and native scopes, and demonstrate installation,
   invocation and recovery. Refresh vendor artifacts, native-format evidence,
   generated payloads and their digests in the provider sources. Verify all
   seven rendered trees and the released consumer boundary.
3. **Reconcile platform consumers.** Compare the existing colleague branch and
   current implementations against `#146`, `#155`, `#139` and `#140`. Complete
   canonical corpus/artifact ingestion, the `cli` kind in storage, assessments
   per adaptation, setup provenance and derived beta support tiers. Preserve
   ownership isolation and immutable public versions.
4. **Close concrete account/catalog flows.** Verify private owner/grantee
   artifact access (`#162`–`#164`), setup presentation and service editing
   (`#165`–`#166`), catalog navigation state (`#167`), identity-avatar import
   (`#168`) and exact-artifact context estimates (`#169`). Use real storage
   integration and user-visible tests; unavailable bytes stay unavailable.
5. **Qualify and release the resulting artifacts.** Run the full local gate,
   native six-leg configuration/program/scope/contribution/launch evidence,
   and the live/account-bound slices at their exact identities. Refresh the
   corpus from immutable provider tags. Only then make the coordinated next
   cut and verify indexes, releases, public deployment and clean Git state.

The architecture/product proposals listed below remain distinct from repairing
the current product. A Rust rewrite or a new component taxonomy does not
follow from finding an incomplete deployed user flow.

## Decision-making vision

- Seven setup systems own native harness writes and real software
  install/update/remove; `ai-stp` invokes the same lifecycle mechanically.
- Existing configuration becomes managed only through explicit adoption with an
  exact plan, never through silent ownership.
- The current component vocabulary is the closed `component_type` list in
  `docs/contracts/component-setup-passports.md` and may be extended by a new
  ADR when a proven native form exists.
- The release target is Linux, Windows, and macOS on both architectures —
  `x86_64`/`arm64` — with real-product evidence; bundles remain portable between
  operating systems.
- Package classifiers name all three operating systems. Every new release
  candidate requires retained six-leg evidence at its exact artifact identities;
  a classifier or an older passing matrix does not qualify the new candidate.
- The agent chooses the engineering path within the task. Digest, rollback,
  provenance, and compatibility remain mechanical integrity constraints without
  creating an additional approval round.

## Implemented surfaces (release coordinates in the current checkpoint)

| Area | Observable state |
|---|---|
| Local-first CLI | SQLite registry, passports/revisions, discovery/adoption, selection, bundle, install/status/diff/update/rollback/recovery, machine help, and canonical Skill |
| Platform | `/v1`, PostgreSQL, object storage, queue, authentication/devices, sync, publication, grants/reports, public catalog, article, and SEO projections |
| Web | Landing, catalog/detail, account/device/owner surfaces, content hub, machine projections, and a three-OS test matrix |
| Providers | Seven provider integrations with native configuration, backup/recovery and software lifecycle interfaces. Current consumer contracts still name protocol v3; per-provider launch completeness requires G4/G5 evidence. |
| Release | Released consumer line is `ai-stp-cli==0.0.28`. GitHub attested acquisition remains the default provider path; PyPI provenance is a second, explicit path (`ADR-0141`). Self-update of the CLI wheel is `SPEC-072` / `ADR-0170`. Source integration, package publication and installed PATH identity are separate observations. |
| Catalog | The canonical first-party corpus models seven harness families and four postures. Identity projection, exact target assurance, and normal-path publication/readback evidence are implemented in the current platform closeout for `#146`/`#155`. |
| OBT support tiers | All seven harnesses are `beta` (`SUPPORT_TIERS`, `SPEC-033` REQ-3315). `primary` remains a valid later GA label with no current members |

## Verified snapshot: 2026-09-02, updated at the 0.0.15 cut

This section retains the earlier measurement narrative, including its package
versions and host claims. It was not re-executed by the 2026-09-06 source audit
and must not be used as evidence for the current `main`, current host health,
or the forthcoming 0.1.0 cut. The later recorded consumer line is `0.0.18`.

- The canonical development checkout is `ai-engineers-guild/ai-stp`. The private
  underscore tree is an archive: it runs no workflows, promotes nothing, and its
  README names where the work went.
- Published Python packages are `0.0.15` — five exact distributions through PyPI
  Trusted Publishing with attestations, SBOMs/checksums and a clean-install smoke
  check, cut from tag `v0.0.15` (commit `2af9122b`). The six-leg slices on that
  exact SHA against providers `0.0.55` passed every Linux and macOS row — 7 of 7
  in configuration and program, 2 of 2 at workspace scope — and failed every
  Windows row, which is the first measurement of the AppContainer holding a real
  provider and is recorded under P0 below. `0.0.14` remains the last version
  whose six legs were all green.
- The active provider release is `0.0.58` across all seven public setup-system
  repositories, each with six native binaries and `SHA256SUMS`, cut on
  2026-09-02 by the provider estate's own agent session in step with this
  side. Four releases landed that day, each answering something measured
  here: `0.0.54` declared `plan_request_fields = [target_scope, end_state]`
  and cursor's `project` profile beside antigravity's; `0.0.55` made `status`
  accept `--target-scope` and refuse by name a plan whose scope contradicts
  the target's record; `0.0.56` declared `status_request_fields:
  [target_scope]` on provider kit `0.2.9`; `0.0.57` validates a kind declared
  only at a scope under that scope, and falls back when `canonicalize` cannot
  answer inside an AppContainer, which is what turned both Windows legs green.
  `0.0.58` gives `remove` a three-part rule — a record removes, an empty target
  is a silent no-op, and declared entries with no record are refused by name
  with the list of what would have been taken — which this consumer meets in
  the race the provider's own record makes possible: that record sits outside
  the target's identity, so it can disappear between a plan and the apply that
  plan authorised without moving the digest that bound them.
  `just evidence-providers 0.0.55`: seven conformant, no projection
  disagreement against the rules below.
- All five evidence slices are green against `0.0.58`, read from the artifacts:
  configuration 42 of 42 with 84 of 84 observe stages, workspace scope 12 of
  12, `user_root` 30 of 30, program 42 of 42, each on all six native legs; and
  the contribution slice 4 of 4, where codex keeps the person's own key through
  the removal. The first-party corpus rebuilt at those seven tag commits moves
  nothing: `changed 0, unchanged 71`.
- `software-evidence` — the consumer driving `harness install/status/update/
  remove` through `ai-stp` itself — is green on **all six native legs** against
  `0.0.53`, seven harnesses each. The one-leg limitation this document carried
  since August is closed.
- Package OS classifiers are Linux, macOS and Windows on the published `ai-stp-cli` distribution;
  the evidence that gated them exists.
- The first-party corpus is published whole: 99 of 99 objects, zero blockers,
  and `just evidence-live` exits 0 against the served generation.
- The account-bound slices ran with a real browser device-code login:
  `evidence-sync` 5/5 verified on two devices, `evidence-publication` verified on
  both its reading and its writing half.
- `nginx` is the only edge proxy (`ADR-0135`); Caddy is gone from the host and
  from every active configuration.
- Isolation launchers exist and are proved on all three operating systems:
  Bubblewrap on Linux; the AppContainer launcher on Windows (`ADR-0133`), now
  proved on a hosted `windows-latest` runner rather than only on the elevated
  machine of the ADR's measurement — the native spawn test drives the real
  `run`, and a parent killed mid-run loses its isolated tree to the job object
  and its grants to the next discovery's sweep; `sandbox-exec` on macOS, whose
  deny-write half is probed with a positive control on every discovery and
  measured on `macos-latest`.
- A bundle and a plan are compiled for one chosen projection scope
  (`REQ-632`): `--scope project` routes onto the workspace surfaces antigravity
  and cursor declare, `--scope user_root` onto the shared `~/.agents/skills`
  root pi, opencode, cursor and grok-build declare, and a home compile is
  byte-identical to before. Both scopes are measured against `0.0.57` on every
  leg: `project` 12 of 12 rows, `user_root` 30 of 30.
- A `/v1` response model accepts the additions its own published schema
  promises. Twenty-six did not, and the first optional field the platform
  added to a card made every released client refuse the whole search body —
  a defect an installed CLI cannot be rescued from, only upgraded past. The
  rule is now a contract test rather than a docstring.
- A contribution's removal hands the provider the bytes that survive it
  (`ADR-0129`, `#54`, closed): the host file without the contributed key,
  packed as a bundle the remove plan must name as that path's `final_bytes`.
  Measured against codex `0.0.57`: the person's own key and comment stayed in
  `config.toml` while the contribution left it.
- The first-party corpus is read at one resolved commit per provider
  repository. These repositories are rendered from a monorepo, so `main` is
  republished whole on every release; a build that read it once per repository
  captured two provider generations while a render was landing, and its own
  drift check agreed with it because both dereferenced the same moving ref.

Use the exact SHAs, run IDs and retained artifacts behind each historical
measurement. Different slices have different denominators: configuration and
program each had 42 cells, workspace 12, user-root 30, and contribution 4.
Do not summarize those distinct measurements as every slice passing 42/42.

## Earlier remaining-work assessment (historical)

Do not carry forward blanket closure of A01–A22 or B01–B04. Current source
contains substantive repairs, including multi-root cancellation/compensation,
adoption reconciliation, autonomy policy, and the safety cache/singleflight
changes associated with `#117`/`#118`. Each wider completion still needs its
own evidence.

The producer-only closures of `#125` and `#127` did not prove their platform
consumers. Those consumers and the `#111`/`#112` assessment path are now included
in the merged platform integration. The additional assessment audit passed its
final gate and merged in `#176`; deployment still needs its served-SHA proof. The OBT target remains standard v1, seven
harnesses, three operating systems, agent-first operation, and an estate record
based on the required evidence.

Prepare the coordinated `0.1.0` cut only after the ordered work is measured.
Never move an existing published tag. Do not invent a
home-override environment variable for Antigravity.

### Closed measurements (not remaining)

The dated snapshot above records earlier configuration, software and scoped
measurements with their separate denominators. Their historical closure is not
reopened merely because a new cut is needed. Their results also do not prove
the latest provider releases, current installed software, or G5's 42 launch
cells. Re-read current release coordinates before executing the next cut.

### OBT assessment — CLI and providers (September 8)

Ordered. Each item is one PR-sized slice unless a later item names a
dependency.

| # | Item | Why it is still open | First proof |
|---|---|---|---|
| G0 | Complete the owned v1 contract cutover | CLI writers on this consumer bind schema bodies and default new plans to live protocol `3`; historical `NULL` stays `1`. Remaining: coordinated provider-estate writers and 0.1.0 tags. | One active owned contract family, coordinated readers/writers, content-bound contract inventory, historical bytes retained without active fallback ambiguity |
| G1 | Setup recast (core value) | CLI source is in tree (transform `1.3`, `#145` / `#147` / `#151`). Pi MCP `projection_kind=package` stays `blocked` (`REQ-6204`) until a measured package transform exists. OBT still needs G4–G6. | Native-positive Claude→Codex case; unsupported syntax is `blocked` or named in `semantic_losses`; files/modes/scopes stay preserved |
| G2 | First-run skill and inventory closure | Inventory continuation keeps authoring `covered` and caps directory listings. Bootstrap uses already-named roots and asks only when none were named. | Provided roots need no repeat question; paged and unpaged fixtures return the same owned objects exactly once, with bounded traversal |
| G3 | Cross-harness component adaptations and executable lifecycle | Component materialize, per-adaptation eval, claimed-portable overlay, and shared `cli` program lifecycle are in tree (`#151`, prefix containment `#152`). Occupied next-minor and overlay identities refuse a different intended passport; install/invoke/status bind to installed bytes and the requested version, not a newer registry `current` or first ZIP member. Setup eval is the setup harness only; `eval component` enumerates every advertised adaptation. `--all-missing` stamps every remaining derivable harness in one owner version. Overlay stays private. Pi MCP packages remain blocked without a measured package transform. | Native format-specific positive and negative controls; one shared executable with verified install/invoke/remove; no sevenfold runtime duplication |
| G4 | Antigravity launch against the documented home | Public `antigravity-setup-system` `main` (`#113`, merge `a4e817de`) declares `LaunchBinding::DocumentedHome`; `config_home_env` stays empty. Six siblings received the shared runtime on the same render. Native `can_launch` against `~/.gemini` is still an evidence run, not this merge. Do not invent `ANTIGRAVITY_*`. | `can_launch` true for the documented home on the published public tree; alternate-root launch still refused by name |
| G5 | Native qualification | Historical `/1` records required 42 launch cells. Current `ai-stp-estate-release/2` requires seven providers on three primary pairs (21 launch cells), per ADR-0172; full setup coverage is 28 × 3. Historical missing rows do not establish the current candidate's result. | Filled estate record with retained evidence; skipped required cells keep the verdict `incomplete` |
| G6 | Coordinated 0.1.0 / OBT cut | Published consumer `0.0.20`, providers `0.0.68`; corpus pins may still name `0.0.67` when bytes are unchanged. Re-resolve those coordinates, then coordinate ai-stp and all seven providers after G0–G5, B01–B08, and the platform dependencies. One standard family is not a relabel of old numbers (`ADR-0154`). | Matching tags, wheel digest, seven provider artifact digests, catalog readback, estate verdict derived from those rows |

### 8 September 2026 CLI beta remainder

Remeasured against public main `185b4549`, PyPI `ai-stp-cli==0.0.20`, production
`git_commit=185b4549` / schema `0053`, and PATH `uv tool` pin `==0.0.17`. The
dated audit is
`/home/rldyourmnd/Developer/guild/ai_stp/plans/2026-09-08-cli-beta-readiness-plan.md`
(archive input only). Requirements stay in specs/ADR/contracts.

Historical J1–J6 / F01–F07 from 7 September remain executed with the limitations
recorded in that day's evidence. They are not re-opened as implementation work.

| ID | Priority | Remainder | Owner / close-out |
|---|---|---|---|
| B01 | P0 | PATH is `0.0.17`; no CLI self-updater | CLI: `SPEC-072` updater, bootstrap from the owning installer, then a normal updater-to-updater transition |
| B02 | P0 | Current corpus exact coordinates return public 404 | CLI publication + platform: ordinary plan/bind/validate/confirm and full readback |
| B03 | P0 | Live private version is `GET /v1/catalog/.../versions/{X.Y}/private`; visibility `/access` is still undeployed | CLI version/artifact client uses the live catalog routes; visibility API remains platform |
| B04 | P0 | `#187` merged `61828fb4`; CLI `/access` version reads were dead against OpenAPI | Same as B03: one live version route, no `/access` fallback for artifacts |
| B05 | P0 | `#187` bind reseals visibility/artifact/revision of an existing `X.Y` | CLI bind and setup publication send sealed passport bytes; catalog projection emits `distribution_visibility=public` for opened private passports |
| B06 | P0 | No current real browser login, two-device sync, grant, private fetch, visibility, revoke | Real sessions; mock transport is not evidence |
| B07 | P0 | 179 commands counted; no current manual command ledger | Ledger against final machine help, including updater commands |
| B08 | P0 | No complete estate record on this line; GitHub `0.0.20` has five assets | Candidate + required evidence cells; incomplete is not complete |
| B09 | P1 | `verify_live_slice` reads one page and one object per kind | Full pagination and exact corpus inventory |
| B10 | P1 | `_evidence.cli` checks JSON `ok` without `returncode` / timeout | Exit/envelope/timeout oracle |
| B11 | P1 | Estate validator does not read artifact files | Executable `--artifacts` or equivalent byte check |
| B12 | P1 | Antigravity launch reasons disagree with released `DocumentedHome` | Re-read exact provider-info; fix the measurement |
| B13 | P1 | `--version` / doctor do not prove plugin/skill/hook/MCP execution | Native loading/invocation probes |
| B14 | P1 | Corpus pins `0.0.67`, runtime providers `0.0.68` | Byte compare; do not bump `X.Y` for a tag-only change |
| B15 | P1 | Roadmap/release docs mixed `0.0.18` / `0.0.65` / unfinished PyPI deletion | This table and the release row; historical snapshot stays historical |
| B16 | P1 | “Everything through PyPI” vs GitHub-default provider acquire | Qualify each layer; no silent source fallback |
| B17 | P1 | Native workflows used checkout consumer, not the published wheel | Matrices install the exact candidate wheel |
| B18 | P1 | PyPI classifier is still Alpha | Beta classifier only after acceptance |
| B19 | P2 | Serena core memory points at missing current-work files in some trees | Drop false pointers; do not revive the archive |

Private/visibility: live private version/artifact reads use the deployed
`/v1/catalog/.../private` and `/artifact` routes. Visibility plans stay on
`/v1/access/visibility/plans` and are not in the current OpenAPI. `#187` is
merged (`61828fb4`); publication bind must not rewrite sealed `X.Y` identity.

Posture (`minimal` / `baseline` / `full-auto` / `nddev-builder`) is the
content footprint of a setup (`ADR-0130`). `execution_profile` is independently
always `full-auto`. A08 already put ask-nothing autonomy keys on every standard
posture. Do not treat the four postures as four execution characters.

v1 is the first product version. There is no generation-to-generation port of
incompatible objects. Old published bytes stay immutable and are never mistaken
for the new standard family.

### OBT remaining — platform/web

The platform closeout for #146/#155 is implemented in the current tree. This
table keeps only the remaining work and records the evidence boundary for the
completed rows:

| Issue | State | Evidence boundary or remaining action |
|---|---|---|
| `#100` | closed for publication | `https://pypi.org/pypi/ai-stp-sources/json` returns 404. Re-deletion is not required. The four other former internal projects also 404. |
| `#125` → `#146` | closeout implemented; GitHub status is maintained separately | Canonical component taxonomy includes `cli` and continues to reject `marketplace`; migration `0033` remains unchanged. |
| `#127` → `#146` | closeout implemented; GitHub status is maintained separately | Fixture seeding remains dev/test only; canonical first-party publication uses the authenticated publication tool and requires catalog/object-store readback and setup provenance evidence. |
| `#111` `#112` → `#146` | closeout implemented; GitHub status is maintained separately | Exact adaptation/scope assessments, worker projection scans, target matrix, and exact-only harness filters are owned by the current platform path. |
| `#155` | implemented in current platform closeout | Public catalog is exact-only; assessment identity is server-validated and target-bound; latest is atomic; recommendations mean current verified full-auto eligibility. |
| `#117` `#118` | source repairs present | Cache admission/freshness and shared in-flight task ownership changed. Preserve the regression tests; do not infer all platform work completed from these two fixes. |
| `#139` | implemented | Setup detail and exact-version pages show `ported_from` as an exact-version link and `related_setup_ids` as separate setup links. Null lineage is omitted. |
| `#140` | implemented | Search rebuild derives tiers from the shared registry and no longer invents `primary`. Bootstrap rebuilds existing rows; web harness/type facets derive from generated contracts and fixture defaults are all-beta. `primary` remains a valid empty OBT filter. |
| `#165`–`#166` | implemented | Both object kinds share owner presentation routes, full public bio/media readback and atomic search refresh. Service editing has separate labeled groups. Upload forwarding enforces CSRF and a streamed byte limit; private media requires its owner. |
| `#167` | implemented | Detail links preserve the catalog query in a validated local `return_to`; the back link restores filtering, sorting, page and view. |

| `#168` | implemented and deployed | Provider avatar import validates bounded image bytes and stores normalized metadata-free media; real decoder, ASGI, and browser UI regressions pass. |
| `#169` | implemented and deployed | Exact stored artifacts and original passport seals drive context estimates; incomplete, corrupt, runtime-only, and unavailable measurements have distinct UI explanations. |
| `#162`–`#164` | open | Complete linked-recipient authorization, private metadata/artifact acquisition, and real S3 durability/race evidence; keep public reads credential-free. |

Backlog issues `#18`–`#60` stay backlog.

### P4. Agent-first cleanup as a continuing practice

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
| Protect `ai-stp/main` (GOV-001) | ADR-0180 restores protected `main`, default `dev`, promotion checks, and administrator bypass with zero mandatory approvals. |
| Six-package publication (REL-002) | Superseded by `ADR-0146`: one public `ai-stp-cli` wheel. Historical six-package artifacts stay immutable. |
| Provider-owned multi-root commit (LAY-002) | Superseded by `ADR-0145` / SPEC-058: the consumer owns a recoverable transaction over unchanged provider v3 (one target). |
| PyPI as the default provider channel (PYP-002) | Not claimed. GitHub attested releases remain the default until six-leg evidence exists for the index path. |
| Public provider disclosure (PUB-001/002) | Owned by the provider estate, not this consumer. Public documentation remains self-contained. |
| Persist adaptation assessments (CMP-003) | Implemented by the target-bound assessment history/latest model and migration `0050`; PostgreSQL concurrency evidence is required at release time. |
| Catalog/web per-harness matrix (CMP-004) | Implemented by exact adaptation target matrices and exact-only harness filters; aggregate fields remain compatibility-only. |
| Scaffold v5 (SCA-001) | Historical milestone, superseded by the `/6` writer below: `source/AGENTS.md` canon, generated `projections/<harness>/` in the native layout, no speculative adaptation document, no invented passport tags, and one reported Git root. |
| Portable hook handler (`#116`) | Done: `component-scaffold/6` writes the derived closed-set manifest and runnable handler under `source/` for portable hooks; `/5` remains validatable. `setup-scaffold/5` embeds `/6`. |
| Authoring freeze (SCA-004) | Done: `setup-scaffold/5` points nested members at `projections/<harness>` with `managed_paths`; compose and `component version release` refuse `TODO(ai-stp-scaffold):` markers and freeze a content-addressed `ComponentAdaptation` on the exact provider surface. |
| Setup export (SCA-003) | Done: `setup export` writes a separate `ai-stp-setup-export/1` review tree whose manifest binds the recorded passport, definition, and every exported file; it mutates neither authoring nor harness state. |
| Control-plane Skill package (`#97`) | Done: `skill install` writes `SKILL.md` plus `references/` for every harness; projections carry the procedure; Russian is a generated locale; machine help still owns flags (`ADR-0149`). |
| Rust rewrite / further component kinds | Separate backlog. The ninth `cli` kind already exists under `ADR-0155`; its existence does not prove runtime lifecycle completion. Historical experiments are not current evidence. |

`#160` published `ai-stp-cli==0.0.18` from candidate `34060185329`, tag `v0.0.18`,
commit `4aa64c36`. A clean index install returned `cli_version: 0.0.18` and
accepted `reset`. `#100` published `0.0.17` from candidate `33850604873`, tag
`v0.0.17`, commit `9e03ab27`. Obsolete GitHub `pypi` / `pypi-*` environments
except `pypi-cli` are removed. `#100` now has one authorized remaining task:
delete `ai-stp-sources` from the owner's PyPI settings. The four other former
internal projects return 404 as measured on 2026-09-07. A fresh uncached
`ai-stp-cli==0.0.18` installation has one first-party distribution, no internal
`Requires-Dist`, and working imports of all bundled runtime namespaces. The
browser denied access to PyPI because administrative policy could not be verified;
the remaining deletion is blocked, not complete. Internal source modules remain
workspace boundaries inside the single public CLI wheel.

## Explicitly out of scope for this pass

The open roadmap items—corporate hub, SSO/GitLab, bot protection, malware
integrations, discovery standards, illustrations, and possible new component
kinds—remain backlog. They are not defects in the current release and are not
closed to satisfy an empty counter. Promotion starts with a check against the
current product and a new active specification.

## Done

Work is complete when current public/private bytes are synchronized, the required
three-platform evidence is executed on exact releases, live slices refer to the
deployed SHA, documentation is generated from its owners, and the final diff and
Git state are clean. `not_verified` is an honest remaining result, not a reason
to add a manual approval or hide a matrix row.
