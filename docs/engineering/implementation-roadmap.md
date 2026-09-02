---
description: "Current ai_stp status and the ordered plan for remaining work."
last_verified: "2026-09-01"
---

# Current status and plan

This is the sole owner of the current plan. GitHub issues remain backlog, ADRs
record decisions, and specifications define requirements; review and session
plans are not continued literally after the implementation changes.

## Decision-making vision

- Seven setup systems own native harness writes and real software
  install/update/remove; `ai-stp` invokes the same lifecycle mechanically.
- Existing configuration becomes managed only through explicit adoption with an
  exact plan, never through silent ownership.
- The current component vocabulary has eight kinds and may be extended by a new
  specification when a proven native form exists.
- The release target is Linux, Windows, and macOS on both architectures —
  `x86_64`/`arm64` — with real-product evidence; bundles remain portable between
  operating systems.
- Package classifiers name all three operating systems; the six-leg evidence
  that gated them exists and is re-run on every release candidate.
- The agent chooses the engineering path within the task. Digest, rollback,
  provenance, and compatibility remain mechanical integrity constraints without
  creating an additional approval round.

## Implemented

| Area | Observable state |
|---|---|
| Local-first CLI | SQLite registry, passports/revisions, discovery/adoption, selection, bundle, install/status/diff/update/rollback/recovery, machine help, and canonical Skill |
| Platform | `/v1`, PostgreSQL, object storage, queue, authentication/devices, sync, publication, grants/reports, public catalog, article, and SEO projections |
| Web | Landing, catalog/detail, account/device/owner surfaces, content hub, machine projections, and a three-OS test matrix |
| Providers | Seven protocol-v3 systems, native configuration layouts, backup/recovery, software lifecycle capabilities, and five complete launch capabilities |
| Release | All five Python packages published through Trusted Publishing (the exact version is in the snapshot below); public `check` and CodeQL green on the verified main; the host pulls `deploy/prod` |
| Catalog | Seven harness families and four postures published; review tasks `#408`, `#456`, `#460`, and `#461` closed by implementation |

## Verified snapshot: 2026-09-02, updated at the 0.0.15 cut

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
- The active provider release is `0.0.57` across all seven public setup-system
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
  `just evidence-providers 0.0.55`: seven conformant, no projection
  disagreement against the rules below.
- `software-evidence` — the consumer driving `harness install/status/update/
  remove` through `ai-stp` itself — is green on **all six native legs** against
  `0.0.53`, seven harnesses each. The one-leg limitation this document carried
  since August is closed.
- Package OS classifiers are Linux, macOS and Windows in all five distributions;
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

Exact SHAs and run IDs intentionally remain in GitHub, Git and evidence
artifacts. This dated section is replaced at the next audit rather than
accumulating snapshots.

## Remaining work

### P0. The configuration lifecycle on all six native legs — measured

`software-evidence` proves the **program** lifecycle on six legs. The
**configuration** lifecycle — the arc this product exists for — was proven by
hand on `linux/x86_64` alone:

```text
seed a native surface → component adopt → component version release
→ select propose → select confirm → install plan → install approve
→ install apply → target status/backups
→ install plan --action remove → approve → apply → the surface is gone
```

`just evidence-config <tag>` and the `config-evidence` workflow drive it, one row
per harness, with the verdict read from the target rather than from the
provider's reply.

Measured against providers `0.0.57`, run `33623425620`, read from the six
artifacts rather than the badge — 42 of 42 rows and 84 of 84 observe stages
passed, with a real isolation launcher named on every leg:

| leg | rows | isolation |
|---|---|---|
| linux `x86_64` / `arm64` | **7/7** | Bubblewrap |
| macOS `x86_64` / `arm64` | **7/7** | `sandbox-exec` |
| windows `x86_64` / `arm64` | **7/7** | AppContainer, and it is doing its job: the positive control reached IPv4, IPv6 and DNS UDP, the container denied all three, and the provider ran in a job object that kills its tree |

That last row is the one this section existed for. It was `unavailable` in
every earlier measurement, then red for two provider releases after the
launcher was proved on a hosted runner. The arc below is what the three
Windows failures were, in the order they were found.

The first run of this slice reported success on all six legs while four of them
had proven nothing: `clean` asked "did nothing fail" rather than "did everything
pass", which a run of pure `inconclusive` rows satisfies. Fixed in all three
slices, and a refusal now carries its message and details so a leg diagnoses
itself. The Linux legs then wanted Bubblewrap plus the unprivileged user
namespace Ubuntu 24.04 restricts; both are in the workflow and both legs are
green.

Windows was a product finding rather than an environment one (`#65`, closed):
the AppContainer probe fails on a hosted runner, `install plan/approve/apply`
proceeded through the trusted-release exception, and `target
status/diff/backups` refused — the read path was stricter than the write it
observed, because the observer was the one caller that never consulted a
trusted release. The three reads now establish trust the way the writers do:
a named `--provider-manifest`, the operator's `--unverified-provider`, or the
release the pair was last verified under when the named executable is its
exact bytes (`docs/contracts/provider-release.md`). Both Windows legs read
their targets back under the same trust the install used, and the isolation
record still says the launcher was unavailable.

The slice also drives the import capture path (`from_import=1`), so the
round trip `#63` closed is proven by the same slice as the ordinary path, and
the two chosen projection scopes (`REQ-632`) for the harnesses whose provider
declares a rule at them: `scope=project` measured 2 of 2 rows on **every** leg
against `0.0.57` (run `33624726045`), Windows included.

The first runs with the Windows AppContainer `enforced` on hosted runners
(after the launcher was proved there) failed every Windows row of every slice
against `0.0.55`: `provider-info` read as answering no `protocol_version`,
program installs ended in an internal failure. A branch-only diagnostic run
showed the provider inside the container exiting 0 with a complete JSON
answer while the consumer's invoker reported "did not answer with JSON": the
container's pipe was opened unbuffered, so the bounded single read returned
the child's first chunk, and the child's stderr shared the answer pipe where
every other platform discards it. Both fixed in one change; the native test's
child now answers in two writes with noise on stderr.

That fix moved the failure one step along rather than removing it, and the
step it moved to was not ours. Re-measured against `0.0.55` and `0.0.56`,
every Windows row still failed, for a structural reason: inside an
AppContainer `std::fs::canonicalize` cannot resolve a path, because the DOS
device name it resolves through lives under `\GLOBAL??`, which the
container's device map does not expose. No consumer change can reach that —
the call is the provider's. The provider estate shipped the fallback in
`0.0.57`: canonicalize when it answers, the joined absolute path without the
`\\?\` prefix when it does not, and the operating-system error in `detail`.
Both Windows legs went green on it, in the configuration slice, the program
slice and the workspace scope. `0.0.15` on PyPI still carries the consumer
half of the pipe defect for any Windows machine whose AppContainer probe
passes, so `0.0.16` follows this measurement.

Remaining in this section: the aggregated run on each release candidate's
exact SHA (`#56`).

### P1. The last link of the capture round-trip (`#63`)

The path from an imported draft to an installable version exists command by
command — `component version release` on each draft, `select propose` and
`select confirm` over those exact versions — and the wall was one layer down:
the importer stored every member at its harness-root-relative path, so the
compiler met a file-shaped component as a named member and re-rooted a
directory-shaped one under itself. Registration now packages members relative
to the component boundary in adoption's own formats and records the same
`source_name`, `content_format` and `managed_paths` facts, so an imported
setup compiles into the bundle an adopted one would
(`docs/contracts/setup-import.md`). Remaining: a `--from-import` row in the
configuration slice, so the round trip is proven by the same slice that proves
the ordinary path.

### P2. `end_state` on the consumer side (`#54`) — done, measured

`ADR-0125` fixes the order: this CLI accepts the field, the CLI is released, kit
`0.2.8` declares it, providers implement it. All four steps are true, and the
consumer half landed on 2026-09-02: `contribution.withdraw()` reconstructs the
host file without the contributed key by the install's own route (TOML through
`tomlkit`, so the person's comments and order survive; JSON as the object
without the key), `select.compile_withdrawal_bundle()` packs the surviving
bytes of every contributed host the target still holds, and `install plan
--action remove` hands that bundle to a provider whose `plan_request_fields`
declares `end_state` — the plan is then required to name each packed member as
`final_bytes` with its member, digest and length. A host that would end empty
is not packed and goes `removed`; a provider that declares nothing keeps
today's whole-file removal; a graph that contributes to no owned file sends no
bundle. Measured by `just evidence-contribution 0.0.56`, whose removal half
seeds the target's `config.toml` with the person's own key before the install:
codex's plan answered «leave config.toml», apply verified, and the file stayed
with that key and without the contribution; cursor's own file and pi's
extension went whole. The three measured refusal forms of `0.0.54` —
`unsupported_operation`, `unsupported_bundle_format`, `digest_mismatch` — are
the shapes the consumer tests pin.

### P3. Native evidence, now measured

1. Windows job objects and grant sweeping: measured on `windows-latest` in
   `test_a_killed_parent_takes_its_isolated_tree_and_its_grants_with_it` — a
   parent killed inside `run` loses its AppContainer child to
   `KILL_ON_JOB_CLOSE`, and `sweep_abandoned_grants` takes back the ACE the
   dead parent never revoked. On the way there the hosted-runner probe was
   found to have failed since the environment allowlist arrived (`[Errno 203]`,
   no `SystemRoot`/`LOCALAPPDATA`/`TEMP`/`TMP` in the child's block), and the
   native spawn test to have skipped on every green `check`; both are fixed
   and the test fails, not skips, on a GitHub runner.
2. The macOS deny-write profile: the launcher's write probe runs a positive
   control and then the identical child under `profile_for(target)` on every
   discovery, and `test_the_real_sandbox_bounds_a_provider_s_writes_to_its_target`
   drives the public `run` on `macos-latest`. The seven real providers under
   that profile are the macOS legs of the configuration slice, 7/7 each.

### P3b. The host's roll time

One roll of the production host — pull, image build, migrate, bring-up —
measured 29 minutes on 2026-09-01 (run `33562822602`, promote 21:46:04 → host
serving 22:15:03), dominated by building the images on the host. The public
verification now waits for two rolls, because the host deploys serially and
always takes the newest ref. The time itself is the thing to act on next:
images built once in CI and pulled by the host would turn a roll into
minutes, but that moves where bytes are built and needs its own decision
beside `ADR-0103` rather than a bigger wait.

### P4. Agent-first cleanup as a continuing practice

1. Any handler that reads a hidden `confirm` must break the registry-parity test.
2. A local reversible operation uses the exact expected value as confirmation; a
   new boolean is added only for a risk class covered by `ADR-0118`.
3. Do not copy old plans or reviews into active documentation. A new session
   reads this roadmap, the specifications and machine help, then checks them
   against the current bytes.
4. Every evidence script has a recipe that names it. A script nobody can invoke
   is not a check; `verify_contribution_slice` sat unreferenced for a day and its
   first real run found three defects in itself.

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
