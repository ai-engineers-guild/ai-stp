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

## Verified snapshot: 2026-09-01

- The canonical development checkout is `ai-engineers-guild/ai-stp`. The private
  underscore tree is an archive: it runs no workflows, promotes nothing, and its
  README names where the work went.
- Published Python packages are `0.0.13` — five exact distributions through PyPI
  Trusted Publishing with attestations, SBOMs/checksums and a clean-install smoke
  check.
- The active provider release is `0.0.53` across all seven public setup-system
  repositories, each with six native binaries and `SHA256SUMS`. Provider kit
  `0.2.8` (it opens `plan_request_fields` to `end_state`), protocol 3.
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
- Isolation launchers exist on all three operating systems: Bubblewrap on Linux,
  an AppContainer launcher on Windows (`ADR-0133`), `sandbox-exec` on macOS.

Exact SHAs and run IDs intentionally remain in GitHub, Git and evidence
artifacts. This dated section is replaced at the next audit rather than
accumulating snapshots.

## Remaining work

### P0. The configuration lifecycle on the other five native legs

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

Measured on `0.0.53`, run `33545244518`:

| leg | rows | isolation |
|---|---|---|
| linux `x86_64` / `arm64` | **7/7** | `enforced` (Bubblewrap) |
| macOS `x86_64` / `arm64` | **7/7** | `enforced` (`sandbox-exec`) |
| windows `x86_64` / `arm64` | 0/7, all `inconclusive` | `unavailable` |

The first run of this slice reported success on all six legs while four of them
had proven nothing: `clean` asked "did nothing fail" rather than "did everything
pass", which a run of pure `inconclusive` rows satisfies. Fixed in all three
slices, and a refusal now carries its message and details so a leg diagnoses
itself. The Linux legs then wanted Bubblewrap plus the unprivileged user
namespace Ubuntu 24.04 restricts; both are in the workflow and both legs are
green.

Windows was a product finding rather than an environment one (`#65`): the
AppContainer probe fails on a hosted runner, `install plan/approve/apply`
proceeded through the trusted-release exception, and `target
status/diff/backups` refused — the read path was stricter than the write it
observed, because the observer was the one caller that never consulted a
trusted release. The three reads now establish trust the way the writers do:
a named `--provider-manifest`, the operator's `--unverified-provider`, or the
release the pair was last verified under when the named executable is its
exact bytes (`docs/contracts/provider-release.md`).

Remaining: the six-leg run on the release candidate's exact SHA.

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

### P2. `end_state` on the consumer side (`#54`)

`ADR-0125` fixes the order: this CLI accepts the field, the CLI is released, kit
`0.2.8` declares it, providers implement it. The first two steps are done —
`end_state` is accepted and kit `0.2.8` publishes it in `plan_request_fields`.
The argv and schema through which a remove plan carries a per-path end state
belong to the kit revision the provider estate introduces; the consumer's
withdraw reconstruction lands in one change once a provider declares the
field, and a provider that does not declare it keeps today's honest behaviour.

### P3. Native evidence for implemented but unmeasured behaviour

1. Windows job objects and grant sweeping are implemented and tested, but have
   not been measured on a native runner during a real parent kill.
2. The macOS deny-write profile has not been run against seven real providers on
   either architecture.

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
