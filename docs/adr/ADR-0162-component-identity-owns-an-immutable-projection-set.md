---
description: "Decision that one catalog component owns one immutable versioned set of exact harness projections and remains the sole social and usage subject."
last_verified: "2026-09-06"
---

# ADR-0162: Component identity owns an immutable projection set

Status: accepted. Supersedes `ADR-0143` for component identity, versioning, and
projection ownership.

## Context

The same logical skill, instruction, MCP, hook, command, agent, plugin, setting,
or CLI can require different native files and provider surfaces in different
harnesses. Representing those implementations as independent catalog components
duplicates discovery, descriptions, ownership, reactions, statistics, and
version history. Representing them as mutable children lets a published
component silently change after consumers pin it.

`ADR-0143` introduced exact adaptations inside a component version. The catalog,
publication, and web contracts still need one explicit rule for which object is
the product identity, what changes its version, and which interaction counters
belong to it.

## Options

1. Publish one component per harness. This makes native compatibility obvious
   but fragments one logical object and multiplies catalog cards.
2. Publish one component with independently versioned projection children. This
   preserves one card but allows ambiguous combinations of parent and child
   versions.
3. Publish one component whose immutable version closes over the complete set of
   exact harness projections available in that version.

## Decision

Option 3 is accepted.

A `Component` is the stable logical catalog identity. A
`ComponentVersionPassport` owns a non-empty set of exact `ComponentAdaptation`
records. Each adaptation names one canonical harness and carries the complete
scope-specific native implementation closure already defined by the supported
passport form: projection artifact, implementation mode, transform identity
when derived, provider-native kind, provider surface, supported target matrix,
technical-support declaration, semantic losses, members, ownership, write and
withdrawal semantics, and permissions.

There is at most one adaptation per harness in one component version. A setup
selects exactly one adaptation whose harness equals the setup harness; no
ordering, origin harness, card default, or provider capability chooses between
adaptations.

The version digest closes over the logical source and every adaptation manifest
and referenced artifact identity. Adding, removing, or changing one adaptation,
projection, declared scope, transform, limitation, permission, or semantic loss
creates a new immutable component minor version under the same stable component
ID. Unchanged adaptations may be referenced byte-for-byte from the preceding
version. A projection does not have an independently publishable version.

The component stable ID is the sole catalog interaction subject. Description,
owner, public page, likes, reports, aggregate views, and aggregate downloads are
component-level. Per-harness usage is a dimension of the component aggregate,
not another reaction target. Adaptations do not receive public pages, likes,
owners, or popularity ranking.

List and search return one component row. Detail and exact-version reads expose
the projection set. A card may summarize harness availability but must not pick
one adaptation's projection kind, operating systems, limitations, or assurance
as if it represented the complete component.

## Consequences

- Seven harness implementations can appear as one component and one history.
- Any projection change intentionally advances the component version.
- Setup and bundle identities continue to bind the exact selected adaptation.
- Existing component reactions and counters need no migration to child objects.
- Flat component-level projection fields are compatibility summaries only when
  their value is true for the complete set; heterogeneous values are omitted or
  represented as a set.

## Rejected implications

- One component does not mean one universal implementation.
- An adaptation is not a setup, bundle, catalog object, or verification result.
- A provider route does not synthesize a missing adaptation.
- `origin_harness_id` remains provenance and has no selection priority.

## Revisit conditions

Revisit if independently distributable projection packages acquire their own
ownership, reactions, or release lifecycle, or if a signed native format can be
installed unchanged by multiple harness providers.
