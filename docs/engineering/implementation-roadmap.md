---
description: "Current ai_stp status and the ordered plan for remaining work."
last_verified: "2026-08-31"
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
- The release target is Linux, Windows, and macOS on both architectures with
  real-product evidence; bundles remain portable between operating systems.
- Until that exact evidence is complete, package classifiers remain Linux-only;
  update them after the evidence is complete.
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
| Release | All five Python packages published as `0.0.10`; public `check` and CodeQL green on the verified main; the host pulls `deploy/prod` |
| Catalog | Seven harness families and four postures published; review tasks `#408`, `#456`, `#460`, and `#461` closed by implementation |

## Verified snapshot: 2026-08-31

- The canonical development checkout is `ai-engineers-guild/ai-stp`; the
  private underscore tree imports it through the standard `public-sync` path
  and separately retains private deployment history.
- Published Python packages are `0.0.11`, five exact distributions delivered
  through PyPI Trusted Publishing with attestations, SBOMs/checksums, and a
  clean-install smoke check.
- The active provider release is `0.0.48`, with seven releases containing six
  native binaries and `SHA256SUMS`.
- The core provider surface has 7 × 6 Linux/Windows/macOS × `x86_64`/`arm64`
  lines.
- Software lifecycle and exact-current provider operations are seven systems ×
  6/6.
- Live deployment was restored after `AI_STP_CONTENT_IMPORT_FORBIDDEN`: the
  internal token is owner-only, content import is complete, and the API/web are
  ready. The deployer now checks the token before build/migrate/recreate, so the
  same omission does not stop the running web.

Exact SHAs and run IDs intentionally remain in GitHub, Git, and evidence
artifacts. This dated section is replaced at the next audit rather than
accumulating snapshots.

## Remaining work

### P0. Provider release 0.0.49 closes the `plan_digest` echo gap

`apply-operation` in released `0.0.48` does not return `plan_digest` for
`software_*`, although configuration apply does and
`docs/contracts/provider-protocol.md` requires the same journal, backup, and
plan digest. The consumer required the echo for every operation, so each
`harness install/update/remove` through `ai-stp` failed **after** the program
had already been installed, leaving an `applied_unverified` operation over the
working prefix.

No producer test caught this because the provider did exactly what its own test
suite asserted. The missing consumer-path slice has now been found.

The order is tolerate-then-emit and has already started: the consumer accepts a
missing echo for software operations but still rejects a mismatch. The provider
side belongs to the closed setup-system authoring environment: `0.0.49` adds the
echo to both response forms, after which it will be checked in practice.

The provider side has now shipped as `0.0.49`. `evidence-software` against it
reported 7/7 `passed` and `clean`, with `plan_digest` present in **21 of
21** software results, compared with zero of 21 for `0.0.48`. Tolerance is
no longer load-bearing: every present echo was checked against the plan digest,
and all 21 matched.

After `0.0.49`, the catalog must be reimported: 15 of 28 published setups lag
their source (all seven `nddev-builder` setups and all `full-auto` setups except
Antigravity), so `install plan` still shows posture descriptions that request
additional confirmations.

### P1. Account-dependent live evidence

1. Complete the real browser device flow for two separate file credential
   stores and run the fast-forward, replay, conflict, and merge sync scenarios.
2. With the same account, verify the owner/publication/grant/report read
   surface and local attestation/preview/reachability scenarios.
3. Check catalog installation for seven harnesses/postures and record content
   gaps without fictional objects. Anonymous live, provider `0.0.48`, citation,
   and six-native-release evidence are already complete.

### P2. Native evidence for implemented but unmeasured behavior

1. Run `just evidence-software <tag>` through the consumer path
   (`harness install/status/update/remove`) for seven released providers. It has
   run against both `0.0.48` and `0.0.49` on Linux `x86_64` with 7/7
   `passed` and `clean`, but not on the other five native lines.
2. Windows job objects and grant sweeping are implemented and tested, but have
   not been measured on a native runner during a real parent kill.
3. The macOS deny-write profile has not been run against seven real providers on
   either architecture.

### P4. Agent-first cleanup as a continuing practice

1. Any handler that reads a hidden `confirm` must break the registry-parity test.
2. A local reversible operation uses the exact expected value as confirmation; a
   new boolean is added only for a risk class covered by `ADR-0118`.
3. Do not copy old plans or reviews into active documentation. A new session
   reads this roadmap, the specifications, and machine help, then checks them
   against the current bytes.

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
