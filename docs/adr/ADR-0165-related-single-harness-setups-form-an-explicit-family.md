---
description: "Decision to group related single-harness setups through an explicit catalog family and compare exact versions using a harness-independent invariant digest."
last_verified: "2026-09-06"
---

# ADR-0165: Related single-harness setups form an explicit family

Status: accepted. Supersedes `ADR-0161` only for treating
`related_setup_ids` as the complete catalog relationship view. Supplements
`ADR-0014`; every setup remains harness-specific.

## Context

Setup recast creates a new stable setup for a target harness and records exact
`ported_from` provenance plus related setup IDs. Those passport fields are
directional, may be asymmetric, and do not answer whether several setups still
represent the same logical configuration. Showing them as equivalent hides
drift. Merging them into one multi-harness setup breaks provider and install
boundaries.

## Options

1. Traverse provenance links for every read and assume all reachable setups are
   equivalent.
2. Replace the objects with one multi-harness setup.
3. Keep each setup independent, add an explicit mutable family for navigation,
   and compare immutable version-level harness invariants.

## Decision

Option 3 is accepted.

A `SetupFamily` is a platform catalog object for grouping and navigation. It has
a stable family ID, owner, name, explicit member setup IDs, an exact baseline
setup/version, creation provenance, revision history, and timestamps. Family
membership is mutable metadata and never changes a setup passport, stable ID,
version, access grant, reaction, counter, or install target.

Each setup remains owned, versioned, verified, liked, counted, selected, and
installed independently for exactly one harness. A family is not accepted where
a setup reference is required and has no install bundle, trust line, reaction,
or version number.

Every newly published setup version carries a
`harness_invariant_digest`. Canonical input includes setup purpose, posture,
execution profile, required capabilities, ordered logical members, exact
component versions, and each member's harness-independent logical/source digest.
It excludes setup harness, selected adaptation ID, native path, projection
artifact, provider profile, and packaging details. The digest does not claim
semantic equivalence beyond those declared inputs.

Alignment is calculated against the family's exact baseline version:

- `aligned` when both invariant digests exist and are equal;
- `diverged` when both exist and differ;
- `unknown` when a historical version lacks the invariant;
- `missing` in authorized diagnostics when a referenced member or baseline is
  unavailable; public reads omit inaccessible member identity.

Recast may join the source family only when owner and visibility policy permit.
It retains exact `ported_from`; family membership and alignment are separate
facts. Later versions may diverge without leaving the family. The platform does
not synchronize or merge members.

Catalog setup detail shows the current setup first and accessible family members
by harness with exact version, provenance, and alignment. Composition shows only
the adaptation selected for that setup's harness and its target-bound assurance.

## Consequences

- Related setups become discoverable without changing installation semantics.
- Drift is explicit and version-specific.
- Existing provenance remains immutable and useful for audit.
- Ambiguous historical graphs are not guessed into families.
- Family-level aggregate counts, if ever shown, are labeled derived sums and are
  not stored as reactions.

## Revisit conditions

Revisit if the product introduces an explicit family synchronization workflow,
or if setup identity itself becomes multi-harness through a separate decision.
