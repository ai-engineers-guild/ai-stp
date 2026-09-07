---
description: "Decision to preserve setup provenance in catalog projections and derive open-beta support tiers from one canonical map."
last_verified: "2026-09-06"
---

# ADR-0161: Catalog projections preserve provenance and canonical beta tiers

Status: accepted. The direct presentation of `related_setup_ids` as the complete
relationship view is superseded by
`ADR-0165-related-single-harness-setups-form-an-explicit-family.md`. Immutable
`ported_from` provenance and the canonical OBT support-tier decision remain in
force.

## Context

Setup recast creates a new setup for the target harness and records the source
setup in the immutable version passport through `ported_from` and
`related_setup_ids` (`ADR-0014`). The fields already exist in the passport and
wire contract, but catalog seed defaults, owner reads, and the public setup page
can lose or hide that relationship.

Open beta includes all seven supported harnesses. `SUPPORT_TIERS` is already the
single product source for that decision, while the catalog migration and web
fixtures still contain older assumptions that Claude Code, Codex, and Grok are
`primary` or that only five harnesses exist.

## Options

1. Reconstruct provenance and support status independently in each consumer.
   This duplicates immutable facts and allows seed, API, migration, and web to
   disagree.
2. Keep the existing fields and map, but leave stale consumers unchanged until
   the next catalog rewrite. This makes current rows and fixtures incorrect.
3. Preserve passport provenance end to end and make every catalog projection,
   migration backfill, and web fixture consume the existing canonical sources.

## Decision

Option 3 is accepted.

Published setup passports remain the source of `ported_from` and
`related_setup_ids`. Seed and publication paths store the submitted passport
without replacing those fields; catalog setup version reads and owner version
reads expose them as safe projections. The public setup page renders the source
setup and related setup links as relationships, without offering a sync or merge
action.

The support tier remains independent from evidence state and trust lane. The
catalog search projection is refreshed from `SUPPORT_TIERS` through the same
passport-derived support projection as detail reads. Existing search rows are
re-projected after the shared map changes; no second tier table or hardcoded
primary-harness list is allowed in migration, web code, or fixtures.

## Consequences

- A forward migration corrects the historical `primary` default and backfills
  existing rows from their public passport harnesses.
- Owner and public catalog contracts gain only the provenance fields needed for
  their existing version reads; historical passports remain immutable.
- Web harness filters and fixtures cover all seven supported harnesses, while a
  `primary` filter may legitimately return no rows during open beta.
- Provenance links are informational and do not grant access, merge state, or
  change setup identity.

## Revisit conditions

Revisit if setup provenance becomes mutable metadata rather than passport
content, if a later product decision adds a support tier, or if open beta
changes the canonical support map.
