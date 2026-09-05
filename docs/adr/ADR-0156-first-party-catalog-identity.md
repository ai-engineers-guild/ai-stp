---
description: "Decision that first-party catalog identity is the corpus passport projection, not a weaker id-and-description record."
last_verified: "2026-09-05"
---

# ADR-0156: First-party catalog identity is the corpus projection

Status: accepted.

## Context

A compiled harness bundle records `setup_id`, `setup_version`, and
`component_refs` from sealed passports. A provider local catalog setup
(`setup.json`) records an id and a description. `Applied` therefore permits a
null setup version and empty component refs for catalog installs, because those
identities are not present. Installing the same first-party preset through
ai-stp (bundle) and through the standalone provider (catalog name) could not
agree on status, discovery, or update identity.

The first-party corpus already seals those identities. The missing object is a
compact projection a catalog can vendor without minting identifiers at install
time.

## Options

1. Invent setup versions and component ids when a catalog install is applied.
   Two channels then disagree about the same bytes.
2. Leave catalog installs identity-less. Honest, and too weak for update and
   discovery.
3. Derive a catalog identity from the existing corpus passports and require the
   CLI compile path to keep those ids. Public trees vendor the projection later.

## Decision

Option 3. `catalog_identity(harness, posture)` reads `family()` and emits
setup and component identities already sealed in the corpus, including each
component's `adaptation_id`. No new stable id is allocated. Compiling that
family through `compile_setup_version_bundle` must report the same setup id
and component stable_ids.

Provider `setup.json` remains id-and-description until the authoring renderer
vendors this projection. Platform seeding of a different Sprint-1 fixture set
stays a separate colleague issue.

## Consequences

- CLI and contract tests hold the projection to the corpus and to the compiled
  bundle.
- A public catalog that still omits these fields cannot claim first-party
  identity parity with ai-stp.
- `ComponentRef` is unchanged: adaptation identity lives on the projection
  member, not on the passport reference.

## Revisit conditions

A public provider vendors the projection into `setup.json` and records
`setup_version` / `component_refs` on catalog apply, or the platform seed
switches to `first_party.CORPUS`.
