---
description: "Current ai_stp status and the ordered plan for remaining work."
last_verified: "2026-09-06"
---

# Current status and plan

This is the sole owner of the current plan. GitHub issues remain backlog, ADRs
record decisions, and specifications define requirements; review and session
plans are not continued literally after the implementation changes.

The remaining-work owner tracks current `main`. Recast file identity, modes,
scopes, and native MCP/agent/hook/plugin transforms landed in `#145` / `#147` /
`#151` (transform `1.3`). Shared `cli` prefix containment landed in `#152`.
`#146` tracks platform closure mismatches. Merged PRs are not the OBT release.

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

## Implemented

| Area | Observable state |
|---|---|
| Local-first CLI | SQLite registry, passports/revisions, discovery/adoption, selection, bundle, install/status/diff/update/rollback/recovery, machine help, and canonical Skill |
| Platform | `/v1`, PostgreSQL, object storage, queue, authentication/devices, sync, publication, grants/reports, public catalog, article, and SEO projections |
| Web | Landing, catalog/detail, account/device/owner surfaces, content hub, machine projections, and a three-OS test matrix |
| Providers | Seven provider integrations with native configuration, backup/recovery and software lifecycle interfaces. Current consumer contracts still name protocol v3; per-provider launch completeness requires G4/G5 evidence. |
| Release | Recorded published line is `0.0.17` as one `ai-stp-cli` wheel (`ADR-0146`, tag `v0.0.17`); GitHub attested acquisition is the default provider path; PyPI provenance is a second, explicit path (`ADR-0141`). Current release qualification and deployed state require exact-SHA evidence, not this row. |
| Catalog | The canonical first-party corpus models seven harness families and four postures. Identity projection exists; completion of the platform seed consumer and artifact closure is tracked by `#146`. |
| OBT support tiers | All seven harnesses are `beta` (`SUPPORT_TIERS`, `SPEC-033` REQ-3315). `primary` remains a valid later GA label with no current members |

## Verified snapshot: 2026-09-02, updated at the 0.0.15 cut

This section retains the earlier measurement narrative, including its package
versions and host claims. It was not re-executed by the 2026-09-06 source audit
and must not be used as evidence for the current `main`, current host health,
or the forthcoming 0.1.0 cut. The later recorded consumer line is `0.0.17`.

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

## Remaining work

Do not carry forward blanket closure of A01–A22 or B01–B04. Current source
contains substantive repairs, including multi-root cancellation/compensation,
adoption reconciliation, autonomy policy, and the safety cache/singleflight
changes associated with `#117`/`#118`. Each wider completion still needs its
own evidence.

The claimed `#111`/`#112` completion is not supplied by the cited PR `#122`.
`catalog_support.py` still projects aggregate support at the audited commit.
`#125` and `#127` were closed against producer PRs `#126` and `#128` which
explicitly excluded their platform consumers. `#146`, assigned to the platform
owner, tracks reconciliation and actual completion without duplicating unseen
work. The OBT target remains standard v1, seven harnesses, three operating
systems, agent-first operation, and an evidence-derived estate record.

Prepare the coordinated `0.1.0` cut only after the ordered work is measured.
Never move an existing published tag. Do not invent a
home-override environment variable for Antigravity.

### Closed measurements (not remaining)

The dated snapshot above records earlier configuration, software and scoped
measurements with their separate denominators. Their historical closure is not
reopened merely because a new cut is needed. Their results also do not prove
the latest provider releases, current installed software, or G5's 42 launch
cells. Re-read current release coordinates before executing the next cut.

### OBT remaining — CLI and providers (this side)

Ordered. Each item is one PR-sized slice unless a later item names a
dependency.

| # | Item | Why it is still open | First proof |
|---|---|---|---|
| G0 | Complete the owned v1 contract cutover | CLI writers on this consumer bind schema bodies and default new plans to live protocol `3`; historical `NULL` stays `1`. Remaining: coordinated provider-estate writers and 0.1.0 tags. | One active owned contract family, coordinated readers/writers, content-bound contract inventory, historical bytes retained without active fallback ambiguity |
| G1 | Setup recast (core value) | CLI source is in tree (transform `1.3`, `#145` / `#147` / `#151`). Pi MCP `projection_kind=package` stays `blocked` (`REQ-6204`) until a measured package transform exists. OBT still needs G4–G6. | Native-positive Claude→Codex case; unsupported syntax is `blocked` or named in `semantic_losses`; files/modes/scopes stay preserved |
| G2 | First-run skill and inventory closure | Inventory continuation keeps authoring `covered` and caps directory listings. Bootstrap uses already-named roots and asks only when none were named. | Provided roots need no repeat question; paged and unpaged fixtures return the same owned objects exactly once, with bounded traversal |
| G3 | Cross-harness component adaptations and executable lifecycle | Component materialize, per-adaptation eval, claimed-portable overlay, and shared `cli` program lifecycle are in tree (`#151`, prefix containment `#152`). Occupied next-minor and overlay identities refuse a different intended passport; install/invoke/status bind to installed bytes and the requested version, not a newer registry `current` or first ZIP member. Setup eval is the setup harness only; `eval component` enumerates every advertised adaptation. `--all-missing` stamps every remaining derivable harness in one owner version. Overlay stays private. Pi MCP packages remain blocked without a measured package transform. | Native format-specific positive and negative controls; one shared executable with verified install/invoke/remove; no sevenfold runtime duplication |
| G4 | Antigravity launch against the documented home | Public `antigravity-setup-system` `main` (`#113`, merge `a4e817de`) declares `LaunchBinding::DocumentedHome`; `config_home_env` stays empty. Six siblings received the shared runtime on the same render. Native `can_launch` against `~/.gemini` is still an evidence run, not this merge. Do not invent `ANTIGRAVITY_*`. | `can_launch` true for the documented home on the published public tree; alternate-root launch still refused by name |
| G5 | Native 7 × 3 OS × x86/arm qualification | Estate record `ai-stp-estate-release/1` already refuses `complete` without 42 launch cells. Installed-artifact and launched-process rows remain `NOT_MEASURED` on current main. | Filled estate record with retained evidence; skipped cells keep the verdict `incomplete` |
| G6 | Coordinated 0.1.0 / OBT cut | Consumer `0.0.17`, providers `0.0.65`, first-party objects at mixed `1.0`/`1.x`. Re-resolve those coordinates, then coordinate ai-stp and all seven providers after G0–G5 and the platform dependencies. One standard family is not a relabel of old numbers (`ADR-0154`). | Matching tags, wheel digest, seven provider artifact digests, catalog readback, estate verdict derived from those rows |

Posture (`minimal` / `baseline` / `full-auto` / `nddev-builder`) is the
content footprint of a setup (`ADR-0130`). `execution_profile` is independently
always `full-auto`. A08 already put ask-nothing autonomy keys on every standard
posture. Do not treat the four postures as four execution characters.

v1 is the first product version. There is no generation-to-generation port of
incompatible objects. Old published bytes stay immutable and are never mistaken
for the new standard family.

### OBT remaining — platform/web (colleague)

Do not implement `apps/api`, `apps/platform`, `apps/worker`, or `migrations`
here. Issues:

| Issue | State | Remaining for the colleague |
|---|---|---|
| `#100` | open | PyPI distribution leftovers (delete the five former internal index projects). CLI install path is already `uv tool install ai-stp-cli`. |
| `#125` → `#146` | closed in GitHub; implementation gap on audited main | `_COMPONENT_TYPES` still excludes `cli`; verify the Postgres CHECK and implement a forward migration where required. PR `#126` explicitly excluded this platform work. |
| `#127` → `#146` | closed in GitHub; consumer not completed by cited PR | `load_first_party_seed` still consumes Sprint-1 fixtures. Seed canonical identities and retrievable artifact bytes, preserve provenance, and derive support tiers. PR `#128` explicitly excluded this platform work. |
| `#111` `#112` → `#146` | closed in GitHub; cited implementation is insufficient | Locate the actual assessment persistence/migration and per-harness matrix implementation, then complete the current server/web consumers. |
| `#155` | open | Persist per-adaptation assessments from CLI coordinates. Do not collapse `component_verified` from the first projection. No catalog `portability_claim`. |
| `#117` `#118` | source repairs present | Cache admission/freshness and shared in-flight task ownership changed. Preserve the regression tests; do not infer all platform work completed from these two fixes. |
| `#139` | open | Setup detail must show `ported_from` and `related_setup_ids` (generated types already have the fields; web mocks them as null and does not render them). |
| `#140` | open | After the shared all-beta map in PR `#141`, catalog search/web must not hardcode three `primary` harnesses. `support_tier=primary` may be empty during OBT; that is correct. |

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
| Protect `ai-stp/main` (GOV-001) | Refused by `ADR-0115`: the gate proves the tree; branch protection would block the agent that writes `main`. |
| Six-package publication (REL-002) | Superseded by `ADR-0146`: one public `ai-stp-cli` wheel. Historical six-package artifacts stay immutable. |
| Provider-owned multi-root commit (LAY-002) | Superseded by `ADR-0145` / SPEC-058: the consumer owns a recoverable transaction over unchanged provider v3 (one target). |
| PyPI as the default provider channel (PYP-002) | Not claimed. GitHub attested releases remain the default until six-leg evidence exists for the index path. |
| Public provider disclosure (PUB-001/002) | Owned by the provider estate, not this consumer. Public documentation remains self-contained. |
| Persist adaptation assessments (CMP-003) | Closure not established by PR `#122`; platform follow-up `#146` retains the requirement from `#111`. |
| Catalog/web per-harness matrix (CMP-004) | Closure not established by PR `#122`; platform follow-up `#146` retains the requirement from `#112`. |
| Scaffold v5 (SCA-001) | Historical milestone, superseded by the `/6` writer below: `source/AGENTS.md` canon, generated `projections/<harness>/` in the native layout, no speculative adaptation document, no invented passport tags, and one reported Git root. |
| Portable hook handler (`#116`) | Done: `component-scaffold/6` writes the derived closed-set manifest and runnable handler under `source/` for portable hooks; `/5` remains validatable. `setup-scaffold/5` embeds `/6`. |
| Authoring freeze (SCA-004) | Done: `setup-scaffold/5` points nested members at `projections/<harness>` with `managed_paths`; compose and `component version release` refuse `TODO(ai-stp-scaffold):` markers and freeze a content-addressed `ComponentAdaptation` on the exact provider surface. |
| Setup export (SCA-003) | Done: `setup export` writes a separate `ai-stp-setup-export/1` review tree whose manifest binds the recorded passport, definition, and every exported file; it mutates neither authoring nor harness state. |
| Control-plane Skill package (`#97`) | Done: `skill install` writes `SKILL.md` plus `references/` for every harness; projections carry the procedure; Russian is a generated locale; machine help still owns flags (`ADR-0149`). |
| Rust rewrite / further component kinds | Separate backlog. The ninth `cli` kind already exists under `ADR-0155`; its existence does not prove runtime lifecycle completion. Historical experiments are not current evidence. |

`#100` published `ai-stp-cli==0.0.17` from candidate `33850604873`, tag `v0.0.17`,
commit `9e03ab27`. A clean index install and one GitHub-attested provider fetch
passed. Obsolete GitHub `pypi` / `pypi-*` environments except `pypi-cli` are
removed. The earlier record assigned deletion of the five former internal PyPI projects
to their owners; current index deletion was not verified by this source audit: `ai-stp-sources`
is `rldyourmnd`; `ai-stp-foundation`, `ai-stp-passports`, `ai-stp-assurance`,
and `ai-stp-contracts` are `artemletya`. There is no deletion API.

## Explicitly out of scope for this pass

The open roadmap items—corporate hub, SSO/GitLab, bot protection, malware
integrations, discovery standards, illustrations, and possible new component
kinds—remain backlog. They are not defects in the current release and are not
closed to satisfy an empty counter. Promotion starts with a check against the
current product and a new active specification.

## Done

Work is complete when current public/private bytes are synchronized, the stated
six-leg evidence is executed on exact releases, live slices refer to the
deployed SHA, documentation is generated from its owners, and the final diff and
Git state are clean. `not_verified` is an honest remaining result, not a reason
to add a manual approval or hide a matrix row.
