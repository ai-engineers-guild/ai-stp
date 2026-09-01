---
description: "Decision to materialize exact external and local component snapshots inside setup definitions."
last_verified: "2026-08-31"
---

# ADR-0140: Embedded component source snapshots

Status: accepted.

## Context

A setup currently pins catalog components by exact `ComponentRef`. Users also
need to use an exact public Git repository, package-registry distribution, or
local component without first publishing a standalone catalog object. The draft
proposed a ZIP setup definition and one resolver shared by setup authoring,
official synchronization, and server verification. ADR-0051 already requires
the setup definition to be independent canonical bytes, while ADR-0083 forbids
external observations from granting trust.

## Options

1. Require catalog publication before composition. This preserves the current
   model but makes one-setup dependencies needlessly public.
2. Add a separate public `ExternalComponent` identity. This duplicates passport,
   validation, graph, and installation rules.
3. Materialize an ordinary exact component passport and bytes inside the setup
   definition, while retaining catalog publication as an optional later action.

## Decision

Option 3 is accepted.

Catalog, embedded external, and embedded local components all end as the existing
exact `ComponentRef`. `ComponentRef` and `SetupVersionPassport.components` do not
gain a source discriminator. A frozen setup rejects an embedded identifier that
collides with a catalog identity. The component passport is resolved from the
catalog or the setup's embedded index, never by name.

ADR-0051 remains in force. `ai-stp-setup-definition/2` is canonical JSON, not a
ZIP, and adds a bounded embedded index containing exact component passports,
source snapshots, and base64url artifact bytes. Its digest remains independent
of the later provider bundle. Content-addressed side objects replace inline
bytes only after a measured size or delivery limit requires them.

A shared internal source-snapshot package owns `SourceIntent`, `SourceSnapshot`,
canonical coordinates, exact-version rules, archive bounds, and adapters for
GitHub, npm, PyPI, crates.io, Go modules, pub.dev, and local paths. Runtime
callers supply transport and credentials; snapshots and logs never contain
credentials. The package is removed if reuse across the CLI, platform, and
official synchronization does not materialize.

An external observation remains untrusted under ADR-0083. Materialization
creates exact bytes and a passport but does not verify upstream authorship. A
setup containing any embedded component is at most `experimental`, even after
the exact bytes pass component checks. Public redistribution fails closed on an
unknown or prohibitive license.

Installation reads embedded bytes from the acquired setup definition and never
contacts an upstream source. Updating an external dependency is explicit and
creates a new immutable setup version. Promotion to a catalog component and
transfer of an official snapshot to a verified upstream maintainer are explicit,
audited operations; setup publication never promotes components automatically.

Catalog presentation follows the same boundary: a setup has no synthetic safety
score. It presents the exact members and their individual checks. Catalog members
link to their catalog identity; embedded Git and package members link to the
canonical external source; local members remain identifiable but unlinked. The
setup keeps one native harness while separately exposing every mechanically valid
harness projection.

## Consequences

- SPEC-057 owns source resolution, embedded materialization, validation,
  acquisition, update, discovery, promotion, and attribution.
- Existing catalog publication, safety checks, provider ownership, and exact
  version rules are reused.
- `ai-stp-setup-definition/1` remains readable; only newly frozen setups using
  embedded components use version 2.
- A rollback may reject creating version 2 but must retain and read already
  stored immutable bytes during the compatibility window.

## Revisit conditions

Revisit when inline artifact bytes exceed an observed setup-definition limit,
when an additional registry is required, or when a registry namespace can be
verified strongly enough to change the trust ceiling.
