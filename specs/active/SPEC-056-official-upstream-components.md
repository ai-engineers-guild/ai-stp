---
description: "SPEC-056: Curated GitHub component snapshots published by AI STP Official."
last_verified: "2026-09-02"
---

# SPEC-056: Official upstream components

## Purpose

AI STP operators can curate a public GitHub component under the AI STP Official
account. Once a day the platform resolves the configured upstream ref, snapshots
exact bytes, runs the ordinary security and publication checks, and publishes a
new immutable catalog version only when the bytes changed.

## Scope

Included: operator-configured GitHub sources, durable source and sync state,
daily idempotent enqueue, exact-commit archive acquisition, reviewed attribution,
and reuse of the existing publication pipeline. Excluded: public management
endpoints, automatic source discovery, automatic ownership transfer, and bypasses
for validation or publication. ADR-0138 owns the exception to ADR-0034; SPEC-057
owns the shared resolver, embedded components, and explicit transfer claim.

## Terms

- `Official upstream source` — an operator-managed record identifying one public
  GitHub repository, tracked ref, safe relative component subpath and type,
  reviewed description, AI STP Official owner, and enabled state.
- `Upstream snapshot` — the exact commit, archive bytes, component-root bytes,
  digest, license observation, and fetch time used for one publication attempt.

## Requirements

- `REQ-5601`: An operator-only local command creates or updates independently
  identified official upstream sources directly in PostgreSQL without a public HTTP endpoint. It
  rejects non-HTTPS GitHub repositories, credentials, an empty or traversing
  subpath, unknown component types, a non-Official owner, and missing reviewed
  attribution text. The write is audited and idempotent.
- `REQ-5602`: A scheduler enqueues at most one `official_upstream_sync` job per
  enabled source and UTC day. The job payload contains only the source ID; GitHub
  credentials and mutable descriptive text do not enter the queue payload. The
  worker process runs this idempotent daily scheduler, so no second daemon is
  required. An operator-only local command may enqueue an additional audited
  retry for enabled sources with a distinct idempotency key; it has no public
  HTTP endpoint, does not enqueue a disabled or missing source, and does not
  replace the daily scheduler key.
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
  create the next unused minor version in the source's stable component line and
  proceed through the shared plan, bind, validate, and publish jobs from
  SPEC-026. No source-specific path writes catalog metadata, verification axes,
  object bytes, or publication lifecycle directly.
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

## States and errors

An official upstream source is `enabled` or `disabled`. A sync records
`unchanged`, `publication_started`, or `failed`; publication lifecycle remains
owned by SPEC-007 and job lifecycle by SPEC-018. Typed failures distinguish an
invalid source, unavailable upstream, changed repository identity, unsafe
archive, failed validation, and an idempotency conflict.

## Security and privacy

The GitHub client follows only validated GitHub repository redirects and never
sends credentials to another host. Archive extraction is bounded and cannot
write outside a temporary directory. Source records, job payloads, logs,
passports, fixtures, and descriptions contain no token or credential-bearing
URL. Server validation independently checks the materialized bytes.

## Compatibility and migration

Additive tables and the new job type follow SPEC-018 and SPEC-020. Existing
catalog objects, first-party launch publication, and experimental seed behavior
do not change. Rollback disables scheduling and source rows remain readable by a
previous deployment; immutable catalog versions are not rewritten.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-5601` | Command/integration tests idempotently upsert two independently identified sources and reject each unsafe coordinate and non-Official owner. |
| `REQ-5602` | Two scheduler runs in one UTC day create one job; the next day creates one more; a same-day operator force creates a second audited job with a distinct key; a disabled or missing `--id` is rejected; payload inspection finds only the source ID. |
| `REQ-5603` | A mocked GitHub archive resolves a ref to a commit and records exact digests; redirect, traversal, link, secret, binary, oversize, and missing-root fixtures fail closed; `.env.example` is accepted while `.env` and `.env.local` are rejected; a skill tree keeps every committed path under the component root, including scripts, assets, docs, tests, and CI. |
| `REQ-5604` | An unchanged snapshot is a no-op; a changed snapshot enters the existing publication flow, publishes once after accepted validation, and a redelivery has no second effect or skipped barrier. |
| `REQ-5605` | The published passport fixture contains the required leading attribution and trailing ownership notice and preserves them on exact-version read. |
| `REQ-5606` | Fetch and validation failures leave the prior version readable; disabling or deleting the source prevents a later enqueue without deleting published versions, audit, or sync history. |
| `REQ-5607` | Catalog API/web tests present publisher and upstream attribution separately and do not label AI STP as upstream author. |
| `REQ-5608` | Two configured sources resolve through the shared Git adapter, enqueue and sync independently, and preserve isolated history on one failure. |

## Required checks

Run `just docs-gen`, `just docs-check`, `just back-static`, and `just back-test`.
