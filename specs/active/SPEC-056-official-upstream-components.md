---
description: "SPEC-056: Curated GitHub component snapshots published by AI STP Official."
last_verified: "2026-09-04"
---

# SPEC-056: Official upstream components

## Purpose

AI STP maintains a reviewable repository inventory of public Git and package
components curated under the AI STP Official account. The platform reconciles
that desired state, records every due update durably, snapshots exact bytes,
runs the ordinary security and publication checks, and publishes a new immutable
catalog version only when the bytes changed.

## Scope

Included: a Git-owned Official manifest, its PostgreSQL projection, durable
source/outbox/job/sync state, scheduled idempotent enqueue, exact source
acquisition, reviewed attribution, reconciliation, transfer fencing, and reuse
of the existing publication pipeline. Excluded: public source-management
endpoints, automatic source discovery, automatic claim approval, and bypasses
for validation or publication. ADR-0139 owns the exception to ADR-0034;
ADR-0153 owns desired-state and delivery architecture; SPEC-057 owns the shared
resolver, embedded components, and explicit transfer request.

## Terms

- `Official upstream source` — an operator-managed record identifying one public
  GitHub repository, tracked ref, safe relative component subpath and type,
  reviewed description, AI STP Official owner, explicit target scope, projection
  root and projection shape, and enabled state.
- `Upstream snapshot` — the exact commit, archive bytes, component-root bytes,
  digest, license observation, and fetch time used for one publication attempt.
- `Official manifest` — the reviewed schema-valid repository file containing
  the complete desired inventory and its exact public identities and sources.
- `Sync attempt` — the durable domain record from one desired update through a
  terminal result, independent of the generic worker job lifecycle.

## Requirements

- `REQ-5601`: A schema-valid manifest in this repository is the complete source
  of desired Official components. Each entry fixes stable ID, globally unique
  canonical name, unique RU/EN display names, component kind, source intent,
  reviewed attribution, enabled state, and update policy under the fixed
  Official account. Reconciliation projects one exact manifest revision into
  PostgreSQL idempotently and audits additions, changes, disables, and removals;
  production rejects an Official source absent from the manifest.
- `REQ-5602`: For every due enabled source, the scheduler creates one sync
  attempt and one outbox event in the same transaction. An idempotent dispatcher
  inserts `official_upstream_sync` into the existing worker queue; the payload
  contains only source and attempt IDs. Daily, manual, and reconcile triggers
  have distinct idempotency keys and never enqueue a disabled, removed, or
  transferred source.
- `REQ-5603`: The worker resolves the configured ref to a full 40-character
  commit, downloads from GitHub with bounded time and size, rejects links,
  traversal, secret-like files, binaries, and missing component roots, and
  records the exact repository identity, commit, archive digest, component
  digest, and observed license. The snapshot is the component subpath as
  committed: a skill includes `SKILL.md` and every other tracked file in that
  directory. Gitignored paths are absent from the GitHub archive and are not
  added; extract does not drop tests, CI, or other committed trees. Committed
  env templates (`.env.example`, `.env.sample`, `.env.template`, `.env.dist`,
  and `.env.*.example`) are not secret-like; `.env` and other `.env.*` files
  remain rejected. A branch or tag is never persisted as version provenance
  without its resolved commit.
- `REQ-5604`: Unchanged component bytes produce a successful no-op. Changed bytes
  are materialized as the source's declared canonical projection, bound to an
  explicit adaptation and provider profile, create the next unused minor version
  in the source's stable component line, and proceed through the shared plan,
  bind, validate, and publish jobs from SPEC-026. A raw component-tree archive is
  not a publishable projection. No source-specific path writes catalog metadata,
  verification axes, object bytes, or publication lifecycle directly.
- `REQ-5605`: Each published description begins with the upstream project name,
  public repository, license, and maintainer attribution and ends with a stable
  notice that AI STP publishes the snapshot for discovery, does not claim
  upstream authorship or affiliation, and will review an ownership-transfer
  request from a verified maintainer. The upstream notice is immutable with the
  version.
- `REQ-5606`: Sync and validation failures are retryable or dead-lettered under
  SPEC-018 without changing the last published version. Disabling or deleting
  the source stops future enqueue but never deletes published versions, audit,
  or sync history.
- `REQ-5607`: `author_verified` and `component_verified` retain their meanings
  from SPEC-007. The UI and machine projection expose AI STP Official as snapshot
  publisher and the upstream attribution separately; neither verification axis
  asserts that AI STP authored or controls the upstream project.
- `REQ-5608`: Git acquisition uses the shared `SourceIntent` and
  `SourceSnapshot` contract from SPEC-057. Multiple enabled source rows are
  independent; one source's failure, disable, or idempotency key does not affect
  another source.
- `REQ-5609`: The sync ledger records desired, queued, resolving, unchanged,
  publishing, published, retry-wait, dead-lettered, failed-permanent, and
  cancelled-transferred outcomes with bounded safe errors, attempt counts,
  source revision, resolved provenance, publication plan, job identity, retry
  time, and timestamps. Queue state does not substitute for domain outcome.
- `REQ-5610`: Periodic reconciliation detects a due source without an attempt,
  an attempt without outbox, outbox without job, queued attempt without live
  job, stale execution, completed job without terminal domain state, and DLQ
  without matching ledger outcome. Repair is idempotent, audited, and uses the
  ordinary dispatcher or retry path.
- `REQ-5611`: The reviewed manifest initially names Ponytail, Caveman, Grill Me,
  Context7 MCP, Serena MCP, AI STP Skill, and every other Official component.
  Each entry is accepted only after its exact source coordinate, component root,
  kind, license observation, attribution, and public names are reviewed; a name
  alone is not a source coordinate.
- `REQ-5612`: An approved ownership transfer atomically changes the catalog-line
  owner, appends ownership and audit revisions, marks the Official source
  transferred and disabled, clears future scheduling, cancels pending outbox and
  queued work, and marks active attempts for cancellation. Resolution and
  publication repeat an expected-owner and ownership-revision fence, so work
  started before transfer cannot publish afterward.

## States and errors

An official upstream source is `enabled`, `paused`, `transferred`, or `removed`.
A sync attempt follows the closed states in `REQ-5609`; publication lifecycle
remains owned by SPEC-007 and job lifecycle by SPEC-018. Typed failures
distinguish an invalid manifest/source, unavailable upstream, changed repository
identity, unsafe archive, failed validation, stale ownership fence, dispatch
failure, exhausted retry, and idempotency conflict.

## Security and privacy

The GitHub client follows only validated GitHub repository redirects and never
sends credentials to another host. Archive extraction is bounded and cannot
write outside a temporary directory. Source records, job payloads, logs,
passports, fixtures, and descriptions contain no token or credential-bearing
URL. Server validation independently checks the materialized bytes.

## Compatibility and migration

Additive manifest, identity, outbox, ledger, and source-state changes follow
SPEC-018, SPEC-020, and SPEC-059. Existing source rows are inventoried and
matched to manifest entries before undeclared production rows are rejected.
Existing catalog objects, first-party launch publication, and experimental seed
behavior do not change. Rollback disables reconciliation and scheduling;
immutable catalog versions and operational history are not rewritten.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-5601` | Manifest/schema and PostgreSQL tests project two independent entries idempotently, reject duplicate identities and unsafe coordinates, and reject an undeclared production source. |
| `REQ-5602` | Scheduler and dispatcher tests commit attempt plus outbox atomically, deliver one idempotent job, preserve distinct manual/reconcile keys, and reject disabled, removed, and transferred sources. |
| `REQ-5603` | A mocked GitHub archive resolves a ref to a commit and records exact digests; redirect, traversal, link, secret, binary, oversize, and missing-root fixtures fail closed; `.env.example` is accepted while `.env` and `.env.local` are rejected; a skill tree keeps every committed path under the component root, including scripts, assets, docs, tests, and CI. |
| `REQ-5604` | An unchanged snapshot is a no-op; a changed snapshot produces the declared canonical projection and explicit adaptation, enters the existing publication flow, publishes once after accepted validation, and a redelivery has no second effect or skipped barrier. |
| `REQ-5605` | The published passport fixture contains the required leading attribution and trailing ownership notice and preserves them on exact-version read. |
| `REQ-5606` | Fetch and validation failures leave the prior version readable; disabling or deleting the source prevents a later enqueue without deleting published versions, audit, or sync history. |
| `REQ-5607` | Catalog API/web tests present publisher and upstream attribution separately and do not label AI STP as upstream author. |
| `REQ-5608` | Two configured sources resolve through the shared Git adapter, enqueue and sync independently, and preserve isolated history on one failure. |
| `REQ-5609` | Failure injection at each stage leaves one accurate ledger state with safe error and retry/DLQ linkage while the last published version remains readable. |
| `REQ-5610` | Fixtures remove each attempt/outbox/job transition in turn; reconciliation restores exactly one next action and records one audit repair. |
| `REQ-5611` | A contract test requires the named baseline entries and validates exact reviewed source metadata for every manifest entry. |
| `REQ-5612` | A concurrent transfer/sync test proves one transaction changes owner and disables work, and no job crossing the ownership fence creates a later Official version. |

## Required checks

Run `just docs-gen`, `just docs-check`, `just back-static`, and `just back-test`.
