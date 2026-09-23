---
description: "Implementation plan for issue #222: deterministic local technology-stack detection in the CLI producing the versioned TechnologyScanHandoff."
last_verified: "2026-09-21"
---

# Local technology detection plan (#222)

**Status: implemented.** `local/tech_detect.py`, `local/tech_findings.py`,
`cloud/technology.py`, migration 44, and the `project detect|technologies|
technology confirm|reject|override|retire|technology mappings|technology
publish` surface now ship the local half. The normative record lives in
SPEC-081 REQ-8212–8216 and ADR-0200;
this document keeps the reasoning and the roadmap it was executed under. The
live requirement is
[ai-stp#222](https://github.com/ai-engineers-guild/ai-stp/issues/222); the
server half it feeds is already shipped under SPEC-081/082 and ADR-0182.

## What already exists (do not rebuild)

| Piece | Where |
| --- | --- |
| `TechnologyScanHandoff` v1 contract (scan_id, scope, complete, detector/mapping versions, observations) | `packages/contracts/src/ai_stp_contracts/technology.py` |
| Evidence model with secret-path refusal (`source`, repo-relative `path`, `reference`, `confidence`, versions) | same file, `TechnologyEvidence` |
| Ingestion endpoint + merge semantics (review survives rescans, absent only after a complete same-scope scan, immutable scan history) | `apps/api/.../technology/detection.py`, `POST /projects/{id}/technology-scans` |
| Org-owned immutable mapping snapshots `(kind, coordinate) → technology_id` | `GET/PUT /technology-mappings/{version}` |
| Bounded project file index (paths, language, digest, exclusions — no secrets) | `local/project_index.build` |
| Canonical seed registry (7 technologies today: Bun, npm CLI, npm registry, GitLab CI/CD, GitLab Runner, React, PostgreSQL) | `technology_seed.py`, SPEC-081 |

## What is missing (the whole local half)

No detector, no mapping consumer, no findings store, no command surface, no
publish leg. Everything below is new code.

## Design decisions to settle in the plan

1. **One walk, not two.** The detector consumes `project_index.build(root)`
   output — paths, language, digests — the same input `symbols.survey` takes.
   Signature rules match indexed paths (manifests, lockfiles, config names,
   container files); content reads stay bounded to matched manifest files
   only, never arbitrary source. Determinism: same tree → same observations.
2. **Mapping is data, not code.** A versioned snapshot maps
   `(kind: package|image|executable|configuration|alias, coordinate) →
   technology_id`. Two sources: a **bundled default** shipped in the wheel
   (offline-first) and the **org snapshot** fetched through the existing GET
   and cached in the registry DB, which wins when present. A signature that
   maps to no canonical identity is still reported — as a finding with the
   coordinate and `unmapped` identity state — but is excluded from the
   handoff, because `TechnologyObservation.technology_id` is required.
3. **The seed gap is named, not hidden.** Of the issue's named set only
   React and PostgreSQL exist in the canonical seed today. Local detection
   still finds Python/Django/FastAPI/Next.js/Angular/Redis/Kafka signatures;
   they publish once the org registry maps them. Extending the seed is the
   registry owner's call (append-only, SPEC-081), not something the detector
   fakes with invented IDs.
4. **Local review mirrors server semantics.** Findings carry review
   (`proposed/confirmed/rejected/overridden`) and freshness
   (`current/stale/absent`). A rescan updates evidence and freshness but
   never resets a review; only a *complete* scan of the same scope may mark
   a finding absent — the same rule the server enforces in `detection.py`.
5. **Publish is a separate act.** `project detect` produces findings and the
   handoff payload; sending it (`technology.scan.publish` permission, exact
   `expected_revision`, linked remote project via `project link`) is an
   explicit flag or a later command, never implicit in scanning.

## Command surface (registry, project group) — as shipped

- `project detect --root <path>` — bounded scan, stores the scan record and
  findings, returns the finding list, the unmapped coordinates, and the exact
  `TechnologyScanHandoff` that publication would send.
- `project technologies` — stored findings for a project with review and
  freshness, per scan scope.
- `project technology confirm|reject|override|retire` — local review on the
  stable `kind:coordinate:context` key that survives rescans; `override`
  requires an explicit `--technology`.
- `project technology mappings list --organization <o>` — every snapshot
  cached for one organization with version, digest and entry count.
- `project technology mappings fetch --organization <o> --version <v>` — fetch
  and digest-cache one exact snapshot. The API exposes exact-version reads, so
  the version is an explicit argument, not "latest".
- `project technology publish --organization <o>` — separate act, separate
  command: projects current publishable findings into the version-1 handoff
  and sends it with `--authorization-revision`, `--idempotency-key`, and
  `--expected-revision` (defaulting to the cached link's remote revision).
  Refuses an unlinked project, a mismatched organization, and a missing
  fetched snapshot before demanding a session.

## Schema — as shipped

Registry migration 44: `tech_scan` (immutable scan records: scan_id,
local_project_id, scope, complete, stopped_by, detector_version,
mapping_version, observed_at), `tech_finding` (per project+scope+kind+
coordinate+context: claims JSON, resolved and override technology IDs,
review, freshness, first/last scan), and `tech_mapping_cache` (per
organization+version: digest, entries JSON, fetched_at).
Migration 45 adds the bounded project index digest as `tech_scan.source_revision`;
old scan rows retain an empty revision and new scans publish it in evidence.
Publication accepts the latest local scan only, since standing findings do not
snapshot historical scan contents.

## Increments

1. **Detector core** — `local/tech_detect.py`, bundled default mapping,
   `project detect --json` (no store/publish). Positive and negative
   fixtures for Python, Django, FastAPI, React, Next.js, Angular,
   PostgreSQL, Redis, Kafka; determinism check (same tree → byte-identical
   findings); secret-path refusal.
2. **Store + review** — migration 44, findings persistence, rescan freshness,
   confirm/reject/override, review survives rescan.
3. **Mapping sync + publish** — fetch/cache org snapshot, `--publish` leg,
   `expected_revision` handling, unlinked/offline refusals.
4. **Normative + qualification** — active spec for local detection, ADR
   (detector consumes the index; mapping snapshots; local review mirrors
   server merge), i18n catalogs, machine-help golden, e2e fixture journey.

## Agent qualification — observed

A weak-model agent (Claude Code, Haiku 4.5, driven through herdr panes)
completed `help` discovery → `project detect` → `technology confirm` →
`technologies` end to end in under a minute, and on the publish leg read
`AI_STP_PRECONDITION_FAILED`, located the link path, checked auth on its own
and stopped at the real blocker without fabricating a workaround. Its single
confusion report — `--project` vs `--root` read as interchangeable — shipped
the `parameter_rules` `exactly_one` declaration plus both-given refusal in
PR #367; the same agent then quoted the rule back and received the named
refusal. Qualification criterion: the surface must be learnable from machine
help alone by a model with no prior exposure.

## Explicit non-goals

No code execution, no dependency installation, no network reads inside a
scan, no `.env`/secret file contents, no ProjectLink creation or mutation
(`#229` owns identity), no forge-language enrichment (`#208` owns backend
enrichment), no model calls.
