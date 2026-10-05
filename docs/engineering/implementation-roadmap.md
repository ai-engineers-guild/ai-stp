---
description: "Current ai_stp status and the ordered plan for remaining work."
last_verified: "2026-10-05"
---

# Current status and plan

This is the sole owner of the current plan. GitHub issues remain backlog, ADRs
record decisions, and specifications define requirements; review and session
plans are not continued literally after the implementation changes.
Checkpoints before 2026-09-29, the session audits of September 24 and 26 and
the closing records are history in
[implementation-roadmap-history.md](../archive/implementation-roadmap-history.md):
true as of their dates, not a queue to replay.

## Remaining work

Ordered by what it unblocks. Each row names the evidence that closes it and
who decides.

| # | Work | Current state | Closes when |
|---|---|---|---|
| 1 | CLI startup floor | Contract models build on first use and local commands no longer import httpx; a local read-only command still costs 1.1–1.3 s of user CPU against the 0.8 s budget (`cli-performance.md`) | `ai_stp_contracts.machine_help` is split so a command imports only the models it returns, measured as in `cli-performance.md` |
| 2 | Desktop sidecar cold start | PyInstaller `--onefile` unpacks the frozen CLI on every call; a `--onedir` freeze measured 0.4–0.5 s faster per call | The CLI ships as a `--onedir` tree through Tauri resources, with `ADR-0222` §7 amended and all three bundles probed |
| 3 | Official manifest curation | 25 of 52 Official sources fail on every daily run: an unsafe archive (binary, link, secret-like path, oversize) or a validation refusal | The maintainer narrows `component_subpath`, replaces, or removes each entry; `failed_permanent` attempts name the code |
| 4 | Worker GitHub token | Unauthenticated Official sync waits out GitHub's rate-limit windows and completes over several hours | Owner decision on `AI_STP_WORKER_GITHUB_TOKEN`, a new credential |
| 5 | PostgreSQL 16 rollback copy | Volume `ai_stp_pgdata` keeps the 16.15 cluster after the 18.6 upgrade | Owner decision to remove it |
| 6 | Desktop code signing | Bundles are unsigned (`ADR-0222` §7) | Certificates exist and distribution requires them |
| 7 | Deferred dependency migrations | `httpx2`, Python 3.14 server images, ESLint 10, `js-yaml` 5, Dependabot for `bun` | Each exit condition in `dependency-policy.md` |
| 8 | Windows process-contract flake | `toolchain harnesses --json` returned no envelope on `windows-latest` on 2026-10-03 and 2026-10-05 | The next occurrence, which now reports exit code and stderr, names the cause |

Not pursued by owner decision: real-agent qualification corpora (GPT OSS 120B
through agy-cli, Claude haiku), native Windows and macOS acceptance runs by an
agent, and scheduled production backups (SPEC-024 `REQ-2409`). Outside this
plan's owner: the Corporate Hub and `[Enterprise]` backlog (#224, #541–#544
and the issues it links) and setup-systems #316.

## Deploy, content and upstream repairs; faster CLI and sidecar — 2026-10-05 (evening)

A ten-day session audit (Codex, Claude Code and Devin; Cursor and Grok had no
ai-stp activity in the window) was checked against production data rather
than CI. Production showed four defects, each repaired with a regression test
and verified on the `79e0dc09` deploy:

- **Deploy outage (`#678`).** The final `compose up` followed `depends_on`: it
  stopped the api and web containers it was recreating, then restarted the
  exited migrate and seed one-shots before starting the new ones. Migrate ran
  three times and seed twice per deploy, and api, web and docs answered 502 for
  about 65 s. `deploy/lib.sh` `start_serving_services` now replaces each
  service once, with `--no-deps`, in order: api, the content import, web and
  docs, the scanner sidecars, the worker. On `79e0dc09` migrate and seed ran
  once, web restarted in 3 s, and the whole deploy produced six 502 responses.
- **Article churn (`#679`).** Every deploy created 46 article revisions, 46 SEO
  builds and a deploy-time `dateModified`, because the revision digest binds
  the snapshot commit. An entry whose content only changed commit keeps its
  revision (SPEC-054 `REQ-5406`). The `79e0dc09` import left the 6,408
  revisions, 5,244 seo_build jobs and generation 203 unchanged.
- **Official upstream refusals (`#680`).** An unsafe archive, invalid source or
  changed repository identity is recorded once as `failed_permanent` instead of
  five downloads from the unauthenticated GitHub budget (SPEC-056 `REQ-5606`).
- **Unserved locale (`#681`).** A crawl of `/ai/content/...` no longer reaches
  the content API and logs an SSR error.

The CLI and the desktop sidecar got faster: contract models build on first use
and local commands no longer import httpx (`#687`; `version --json` 1.75 →
1.13 s of user CPU), and the sidecar freezes without setuptools (`#688`). A
release-equivalent sidecar answered in 2.03 s against 2.93 s for desktop
0.0.5. `#689` stops a session that cannot reach the operating system key store
from offering `device reset` for a key that is only out of reach.

One cost remains in the deploy: the API and the worker finish their own
shutdown within two seconds of SIGTERM — `shutdown` and `worker_stop` are
logged — yet dockerd stops them by force ten seconds later. Neither the
production image in isolation nor a local PID-1 run reproduces it; it adds
about ten seconds to the API restart and loses no work.

## Production repairs, current majors, and PostgreSQL 18 — 2026-10-05

Between the 2026-10-03 checkpoint and this one, `#617`–`#646` shipped
`ai-stp-cli` 0.0.37 and 0.0.38 with desktop 0.0.3 and 0.0.4. They also
carried a five-agent desktop contract audit, a system-wide audit wave
(frozen-guard ordering, shell codes, deploy hardening), a bound on docker
residue after every pull-deploy attempt, and the release-tag membership
check. This checkpoint covers `#649`–`#675`.

**Production repairs, found by reading production rather than CI.**

- **Migration chain (`#664`).** The 2026-09-27 reports/heartbeat merge had
  re-chained an applied revision, so production reached `0111` without
  `0096_heartbeat_reports` … `0106_technology_review_queue`. Five tables,
  six columns and their policies were missing, and `telemetry_retention`
  dead-lettered daily from 2026-09-30. `0112_replay_skipped_feature_chain`
  replays the skipped revisions. Production now reports
  `alembic check: No new upgrade operations detected`, and the retention
  sweep completes. `migrations/history.lock` with
  `tests/contract/test_migration_history.py` makes a changed parent a CI
  failure (SPEC-020 `REQ-2002`).
- **Idle worker (`#665`).** Each idle poll rewrote the 200 oldest
  dead-lettered Official sync attempts: 8.9 million updates and half a core.
  Worker CPU fell from 49.5 % to about 1 %, ledger updates from 120 per second
  to 0, and empty claims are no longer logged.
- **Upstream rate limit (`#666`).** Without a GitHub token, 37–42 of the 52
  daily Official syncs on most days spent all five attempts within fifteen minutes of a
  closed rate-limit window. Retries now wait for `retry-after` or
  `x-ratelimit-reset`, bounded to an hour (SPEC-018 `REQ-1806`, SPEC-056
  `REQ-5606`). A worker token remains an optional owner decision.
- **Readiness (`#673`).** `/v1/health/ready` no longer parses all 119
  revision files per call.

**Dependencies at their current releases**, with every deferral recorded in
`dependency-policy.md` and its exit condition:

- uv 0.12.23 and the Python set with SQLAlchemy 2.1 (`#663`);
- RustFS 1.0.1 (`#651`), container bases and worker-safety scanners
  (`#655`, `#659`, `#660`), Dependabot over container images (`#650`);
- Next.js 16 with Turbopack, plus the web toolchain and lucide-react 1.x
  (`#669`, `#674`);
- desktop on Rust edition 2024 (`#667`);
- PostgreSQL 18.6 (`#670`), moved in by a verified dump-and-restore deploy
  stage (SPEC-024 `REQ-2419`).

Deferred: `httpx2` (TLS trust store), Python 3.14 server images
(`yara-python` wheels), Dependabot `bun` (lockfile v2), ESLint 10 (plugin
peers) and `js-yaml` 5 (tree-wide override).

**Correctness of the web gate.** Next 16 removed `app-build-manifest.json`,
and the page entry it held had left out the layout chunks. The REQ-2213 gate
now measures every module script that the served `/en` page loads: 207 KiB on
Next 15, 229 KiB on Next 16, mostly framework runtime. The budget is 240 KiB.

**Desktop safety.** `#661` delimits process-group signals with `--`.
Desktop 0.0.4's timeout path could make procps-ng broadcast SIGTERM. Process
tests on the development workstation run only inside an isolated PID
namespace.

**Owner decisions.** Production runs no scheduled backup (`#658`, SPEC-024
`REQ-2409`).

**Releases.** `ai-stp-cli` 0.0.39 is on PyPI (wheel and sdist from attested
candidate run 37266590041), with its GitHub Release carrying the SBOM, release
manifest and `SHA256SUMS`. `ai-stp-desktop` 0.0.5 is the repository's latest
release: deb, rpm and AppImage for Linux, an aarch64 dmg, and an exe and msi for
Windows, unsigned as before. Production serves Next.js 16.3.8; its landing page
loads 229.0 KiB of gzipped module JS, the figure the gate measured before
deployment.

**PostgreSQL 18 in production.** The `d02a3af6` deploy ran the upgrade stage
at 06:08 UTC on 2026-10-05. It stopped the writers, restored the 16.15
database into `ai_stp_pgdata18`, verified the row count of all 132 tables, and
brought the stack up on 18.6 within one minute. After the deploy, `alembic
check` reports no drift, the worker completes jobs, and readiness answers in
about 25 ms on loopback (it was about 190 ms). `ai_stp_pgdata` keeps the 16
cluster as the rollback copy; removing it is a separate decision.

## Desktop CI, dependency security, and contract drift — 2026-10-03

Four pull requests landed on `dev` since the 2026-09-29 checkpoint. `#611`
gave the desktop shell its own CI: `desktop.yml` runs the `src-tauri` crate's
fmt/clippy/tests on all three OSes behind a compile-time stub sidecar, then the
real PyInstaller sidecar and a filtered-env spawn test; the `desktop-*` just
group mirrors it locally outside `just check`. `#612` moved Next.js to 15.5.27
for the September 30 security advisories, extended `scan_lockfile.sh` to the
three desktop lockfiles (the unfixable `glib`/`proc-macro-error` findings sit
behind dated `osv-scanner.toml` ignores at the one lockfile that carries them),
repaired the Dependabot `uv` job by normalizing the six mixed-case docs pins
to PEP 503 names, and raised the `httpx` floors to 0.28. `#613` made SPEC-080
name the shipped `technology` intent, completed the HTTP status table with the
thirteen registered codes it was missing and a contract test that parses it
against `http_status_for`, recorded two verified wire facts in `http-api.md`,
applied the catalogue loopback rule to telemetry endpoints, and made the
consent record an owner-only atomic write. `#615` patches the unfixable
`braces` advisory (GHSA-vfj7-8cjw-p6xm) in place — `patchedDependencies` adds
the upstream-recommended nesting-depth guard to the dev-tool installs — with
the scanner exception scoped to the version string it still reports.

In the authoring estate, setup-systems `#382` refreshed all seven vendor pins
(claude 2.1.288, codex 0.160.0, grok 1.0.49, pi 1.0.0, opencode 1.18.34,
cursor 2026.10.01-e373342, antigravity 1.2.15), taught the baseline comparator
to read Mach-O code signatures so a re-signed-but-identical binary reads
`signature-only`, and added pi 1.0.0's `mcp-auth.json` token store to
`never_touch`. `#383` prepares the 0.0.88 release; publication is the next
step.

## Corporate navigation and People & Access design — 2026-09-29

ADR-0219 and active SPEC-095 describe the shared Human sidebar for both profiles.
ADR-0220–0221, proposed SPEC-096–097, and
`corporate-navigation-access-plan.md` retain the remaining access workstream.
The proposed access documents do not replace the current active corporate
specifications. SPEC-095 owns the implemented sidebar behavior. The completed corporate-core foundation plan
is retained in `docs/archive/`. The older workspace consolidation ledger
remains evidence for SPEC-086, not a queue to replay without checking its
current implementation and exact-SHA gates.
GitHub #541–#544 track bounded implementation slices under open program #224.

The 2026-09-30 navigation correction is implemented on
`fix/shared-context-navigation`, preserving prior unfinished access and OIDC
work. It mounts one sidebar in the Human shell for both profiles, adds collapse
and grouped disclosure states, and separates Security from invitations/settings.
A signed-in Chrome profile on local `:3000` supplies live Corporate evidence;
the temporary SaaS preview supplies the second-profile evidence. The detailed
gap table and repair scope are in `corporate-navigation-access-plan.md`.
Remaining People & Access content redesign and policy migration retain their
own exit gates; sidebar completion does not close those work packages.

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
| Providers | Seven public setup systems at `0.0.88`, read through the vendored provider kit `0.2.15` and protocol v3: native configuration, backup/recovery and software lifecycle. Launch completeness per provider is measured evidence, not a property of the release. |
| Release | `ai-stp-cli==0.0.39` on PyPI with its GitHub Release (SBOM, manifest, `SHA256SUMS`). GitHub attested acquisition remains the default provider path; PyPI provenance is a second, explicit path (`ADR-0141`). Self-update of the CLI wheel is `SPEC-072` / `ADR-0170`. Source integration, package publication and installed PATH identity are separate observations. |
| Desktop | `ai-stp-desktop` 0.0.5: a Tauri 2 shell over the CLI machine contract with a frozen CLI sidecar (`ADR-0222`); deb, rpm and AppImage for Linux, an aarch64 dmg, and an exe and msi for Windows, unsigned. |
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
