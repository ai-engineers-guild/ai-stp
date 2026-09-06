---
description: "SPEC-057: Exact external and local components embedded in setup definitions."
last_verified: "2026-09-04"
---

# SPEC-057: Embedded component sources

## Purpose

A user may compose a setup from catalog components and exact GitHub, package,
or local sources without publishing every dependency as a catalog object. Every
non-catalog source is frozen as an exact component passport and artifact inside
the setup definition, validated before publication, and installable without the
upstream service.

## Scope

Included: source contracts and adapters; mixed setup authoring; embedded
materialization; public/private validation; offline acquisition and installation;
explicit dependency updates; name discovery; catalog promotion; official-source
reuse; forks and duplicate-byte suggestions. Excluded: automatic promotion,
automatic dependency updates, a new public component kind, namespace-based trust,
and registries beyond npm, PyPI, crates.io, Go modules, and pub.dev. ADR-0139 owns
the architecture and extends ADR-0051 without changing `ComponentRef`.

## Terms

- `SourceIntent` — bounded authoring input naming `catalog`, `git`, `package`, or
  `path` without asserting trust.
- `SourceSnapshot` — canonical coordinate, exact version or commit, selected
  artifact, digest, metadata, dependency evidence, license observation, and
  provenance evidence.
- `Embedded component` — an ordinary exact `ComponentVersionPassport` and
  artifact stored only in one setup definition; it has no catalog metadata.
- `Embedded index` — the deterministic map from exact `ComponentRef` to embedded
  passport, source snapshot, and artifact bytes in setup-definition version 2.

## Requirements

- `REQ-5701`: The shared source contract accepts catalog identity, GitHub
  repository/ref/subpath, package ecosystem/name/exact version, or a bounded
  local path. It canonicalizes coordinates, rejects credentials and traversal,
  and returns an exact `SourceSnapshot`; it never grants either verification
  axis or target-write authority.
- `REQ-5702`: Git resolves branch or tag authoring input to a full commit before
  freeze. Frozen provenance contains repository identity, canonical URL, commit,
  safe subpath, archive digest, and component digest; a floating ref is rejected.
- `REQ-5703`: Package adapters use only the official allowlisted distribution
  endpoints for npm, PyPI, crates.io, proxy.golang.org with checksum evidence,
  and pub.dev. They pin an exact release and exact file/archive digest plus the
  resolved dependency graph or lock evidence. Registry names are distribution
  sources, not trust authorities.
- `REQ-5704`: npm snapshots record exact version, tarball digest, entry point,
  lifecycle scripts, repository metadata, and dependency lock. PyPI snapshots
  require an explicit distribution filename and supported platform when a
  release has more than one file. crates.io records archive checksum and
  `Cargo.lock` or resolved graph; Go records module version, zip hash, and
  checksum evidence; pub.dev records archive checksum and `pubspec.lock` or
  resolved graph.
- `REQ-5705`: Setup authoring may mix catalog, Git, package, and local-path
  entries. Freeze resolves every non-catalog input, creates or reuses a local
  component identity, builds a complete component passport, writes exact
  `ComponentRef` values to the setup passport, and uses
  `ai-stp-setup-definition/2` only when the embedded index is non-empty.
  A local-path member whose description still carries `TODO(ai-stp-scaffold):`
  is refused before any setup version is recorded.
- `REQ-5706`: Definition version 2 is bounded canonical JSON containing the
  version 1 fields plus sorted embedded passport, snapshot, and base64url artifact
  records. Passport and artifact digests and sizes are independently verified;
  a catalog identity collision, duplicate ref with different bytes, unknown
  field, unbounded payload, or incomplete passport blocks freeze.
- `REQ-5707`: An embedded passport retains the eight existing component kinds,
  exact dependency refs, permissions, required environment, conflicts, source,
  license, and artifact digest. Its owner is the setup publisher as snapshot
  publisher, while upstream project, source, and maintainers remain separate
  attribution. It has no catalog metadata, reactions, publisher page, or direct
  search result.
- `REQ-5708`: A local/private setup may embed public Git, package, and local
  sources. Public setup publication sends the exact definition bytes to the
  server and is rejected when redistribution rights are unknown/prohibited or
  local bytes are not owned by the publisher.
- `REQ-5709`: A setup with any embedded component is at most `experimental`.
  `author_verified` and `component_verified` remain independent per component;
  successful byte checks do not verify the upstream namespace or raise the setup
  to `authoritative`.
- `REQ-5710`: Server setup validation resolves each exact ref from the catalog
  or embedded index. Catalog refs reuse current stored evidence. Embedded refs
  require passport/artifact digest and size checks, source-coordinate validation,
  independent provenance confirmation when network policy permits, the complete
  component safety suite over actual bytes, dependency/conflict checks, and setup
  aggregation. A missing, ambiguous, or mismatched ref fails closed.
- `REQ-5711`: Setup acquisition stores definition version 2 and all embedded
  passports/artifacts atomically in the verified local content store. Install
  and provider compilation read catalog bytes from the AI STP cache and embedded
  bytes from the definition; neither path contacts GitHub or a package registry.
- `REQ-5712`: Upstream availability or a newer release never changes a frozen
  setup. An explicit update resolves the selected newer exact snapshot, reruns
  checks, and creates a new setup version; cancellation leaves the old version
  selected and unchanged.
- `REQ-5713`: A name-only query searches catalog candidates and, only with an
  explicit registry-discovery flag, supported package candidates and known GitHub
  candidates. Results show source, exact candidate coordinate, catalog status,
  and trust separately; ambiguity always requires an explicit selection.
- `REQ-5714`: `component publish --from-setup` extracts one embedded passport,
  artifact, provenance, and digest and enters the ordinary publication plan,
  bind, validate, and publish flow. It reuses the exact passport only when public
  fields, owner, source, and license are complete; otherwise it creates a new
  catalog identity/version. Setup publication never invokes it.
- `REQ-5715`: Official upstream synchronization consumes the shared
  `SourceIntent`/`SourceSnapshot`, supports multiple operator-managed Git and
  package source rows, and retains SPEC-056 scheduling, attribution, idempotency,
  validation, and failure behavior. A matching embedded snapshot remains
  immutable; the CLI may suggest a catalog replacement only when canonical
  coordinate and artifact digest both match and never replaces it automatically.
- `REQ-5716`: Local and GitHub forks remain embedded until explicit promotion.
  Byte equivalence with an official catalog component produces a dismissible
  suggestion, not an automatic identity merge. Similar names never merge
  identities; after freeze, names do not participate in resolution.
- `REQ-5717`: Any authenticated account, including AI STP Official, may request
  transfer of an Official catalog component through the shared private request
  flow. Submission neither requires nor grants `author_verified`. Staff reviews
  the claimant, requested recipient, exact affected line and versions, reason,
  and evidence; approval is performed only by the database-bound operation in
  SPEC-056, while denial has no catalog or source effect.
- `REQ-5718`: All resolver and registry clients use bounded time, response size,
  redirect host, extraction size/count, and dependency-graph limits. Tokens,
  credential-bearing URLs, local absolute paths, and secret-like files do not
  enter passports, setup definitions, queue payloads, logs, or fixtures.
- `REQ-5719`: Catalog setup summaries expose the mechanically supported harness
  projections and never show an aggregate safety percentage. Setup detail lists
  every exact constituent by its human name and version, labels embedded members,
  links catalog members to catalog pages and external members to their canonical
  Git or package source, and shows each member's own safety results. Local members
  have no invented external link.
- `REQ-5720`: After a mixed setup is recorded locally, `setup export` writes a
  review tree of the immutable passport and definition artifact to a new unused
  directory. A canonical `ai-stp-setup-export/1` manifest binds the exact setup
  identity and digest of every exported file without binding the destination
  path. The result names the local registry as storage and does not create a
  physical harness tree, mutate an authoring tree, or write native harness state.

## States and errors

Resolution is `unresolved`, `needs_selection`, `resolved`, or `failed`. An
embedded component is private within its setup and has no independent catalog
lifecycle. Update and promotion use the existing operation/publication states.
Typed errors distinguish unsupported source, floating frozen source, ambiguous
distribution, unavailable source, integrity mismatch, unsafe archive, prohibited
redistribution, catalog collision, missing embedded ref, and stale update.

## Security and privacy

Network adapters are allowlisted and treat all metadata and bytes as untrusted.
Archive and package scripts are never executed during resolution. Local paths are
read only within the confirmed root and are removed from frozen documents. The
server repeats safety validation for public setup bytes; client evidence alone is
not sufficient.

## Compatibility and migration

`ComponentRef`, component kinds, exact version pinning, and definition version 1
remain unchanged. Readers that do not support definition version 2 reject it with
a typed upgrade error rather than ignoring embedded records. Additive contracts
and generated schemas follow SPEC-010 and SPEC-015. Rollback preserves stored
version 2 bytes and published setup history.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-5701` | Contract tests cover every source intent, canonical coordinate, credential/traversal rejection, and false trust flags. |
| `REQ-5702` | Git fixtures resolve branch/tag to commit and reject floating frozen provenance, changed repository identity, unsafe redirect, and subpath escape. |
| `REQ-5703` | Adapter tests contact only each allowlisted endpoint, pin exact artifacts and dependency evidence, and label registry metadata as observation. |
| `REQ-5704` | Ecosystem fixtures cover npm scripts/lock, PyPI file ambiguity/platform, crates checksum/lock, Go checksum, and pub archive/lock. |
| `REQ-5705` | A mixed authoring fixture freezes to exact refs and a version 2 definition; a catalog-only setup remains byte-compatible version 1; a scaffold draft still containing `TODO(ai-stp-scaffold):` is refused. |
| `REQ-5706` | Golden and negative tests verify canonical bytes, ordering, digests, bounds, collisions, mismatches, and incomplete records. |
| `REQ-5707` | Passport tests cover all closed kinds, ownership/upstream attribution separation, dependencies, and absence from catalog search. |
| `REQ-5708` | Private Git/package/local fixtures pass; public fixtures fail for unknown/prohibitive licenses and foreign local bytes. |
| `REQ-5709` | Trust tests prove any embedded member caps the setup at experimental without conflating verification axes. |
| `REQ-5710` | Server process tests validate mixed catalog/embedded graphs, scan actual embedded bytes, and reject every missing/ambiguous/mismatched ref. |
| `REQ-5711` | Acquisition/install tests succeed with all upstream hosts disabled and detect changed local/cache bytes before provider planning. |
| `REQ-5712` | Update tests preserve the old version until explicit confirmation and create one new immutable version for the chosen snapshot. |
| `REQ-5713` | Search tests require the discovery flag, show separated sources/trust, and never silently choose equal names. |
| `REQ-5714` | Promotion process tests use the ordinary publication barrier, cover passport reuse/new identity, and prove setup publish causes no promotion. |
| `REQ-5715` | Multiple official Git/package sources use the shared resolver; exact coordinate+digest yields only a dismissible replacement suggestion. |
| `REQ-5716` | Local/Git forks remain embedded, duplicate bytes suggest without merging, and name collisions retain distinct exact refs. |
| `REQ-5717` | Requester, Official-account, and database-bound transfer tests cover claim evidence, preview, audit, ownership revision, source cutoff, and immutable history. |
| `REQ-5718` | Bounds and secret-redaction tests cover every adapter, archive, graph, document, payload, log, and fixture boundary. |
| `REQ-5719` | Web/API tests cover projected harnesses, absence of a setup percentage, per-member checks, and catalog/Git/package/local link behavior. |
| `REQ-5720` | Export of a recorded mixed setup writes passport, definition, README, and a recomputable export manifest to a new directory; it refuses an occupied destination without mutating either authoring or harness state. |

## Required checks

Each task runs focused tests plus affected canonical checks. Final integration
runs `just docs-check`, `just back-static`, `just back-test`, and `just web-check`.
