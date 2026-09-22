---
description: "The local detector emits coordinates; only a versioned mapping snapshot may resolve them to canonical technology identities."
last_verified: "2026-09-20"
---

# ADR-0200: Local technology detection emits coordinates, not identities

Status: accepted. Implements the local half of #222 against the already-shipped
server side of SPEC-081 (REQ-8205–8208); REQ-8212–8216 record the local rules.

## Context

The platform already owns canonical technology identities, organization mapping
snapshots, and `POST /technology-scans` ingestion with review-merge semantics.
What the CLI needed was a local half: see what a project uses, let the operator
review it, and hand the platform exactly the contract it validates. Three
temptations had to be refused explicitly: walking the filesystem a second time
beside `project_index`, minting `technology_*` identifiers for things the seed
or an organization snapshot never named, and letting source contents travel as
evidence.

## Options

1. Detector over `project_index`, emitting ecosystem coordinates that a
   versioned mapping resolves to identities; unknown coordinates stay unmapped.
2. Detector emits identities directly, keyed by a hardcoded name table: fewer
   moving parts, but the CLI would be minting canonical identities the
   organization never issued — the same fabrication REQ-8205 forbids.
3. Detection delegated to the platform: upload the manifest corpus and let the
   server classify it — violates the local/cloud boundary: manifests are source
   content and the device sends bounded metadata only (SPEC-004 REQ-407,
   SPEC-013).

## Decision

Option 1. The detector is a pure function of the one bounded index: it walks
nothing itself, re-verifies each file's recorded digest before parsing, and
emits `package`/`image`/`executable`/`configuration`/`alias` coordinates with
bounded evidence — repository-relative path, optional wire-safe reference,
source, confidence. Presence-based signatures cite at most eight paths so a
monorepo cannot scale evidence with repository size.

Identity resolution is a separate step over an immutable `MappingSnapshot`.
The CLI ships a bundled table that resolves only the canonical seed identities;
an organization snapshot fetched by exact version overlays it on coordinate
collision. A coordinate no mapping covers stays unmapped — reported, never
smuggled into an observation.

Local review attaches to `kind:coordinate:context`, deliberately without
version, so a rescan that moves a version retains the decision; overrides name
an explicit identity and fabricate no evidence for it. Freshness is
`current`/`absent`/`stale`/`unknown`; only a complete scan of the same scope
marks a previously seen finding absent. Publication projects current,
publishable findings into the version-1 `TechnologyScanHandoff` — one
observation per canonical technology/context, strongest version claim winning —
and requires an explicitly linked project plus a fetched organization snapshot
before a session is demanded.

## Consequences

`project detect`, `project technologies`, `project technology
confirm|reject|override|retire`, `project technology mappings
list|fetch`, and `project technology publish` are the whole local
lifecycle: detect → review → fetch mapping → publish. `project detect` already
shows the handoff resolved the way publication resolves it — the fetched
organization snapshot when cached, else the bundled table — so nothing new is
minted on the wire. What an organization has not mapped reaches the platform
only as an `unmapped` report — the server, not the CLI, decides whether it
deserves an identity.
