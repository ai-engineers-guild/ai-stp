---
description: "Decision to make the passport the sole description of an object and retain a single write path into a harness."
last_verified: "2026-08-04"
---

# ADR-0012: Passport as the sole description and a single write path

Status: accepted.
Refined by `ADR-0021`: fact origin and confirmation are separated into two axes.

## Context

The product goal is for an agent to easily understand and identify any object: a developer, project, component, or setup. This requires each of them to have a machine-readable description.

Two problems emerged. First, a component and a setup were each described twice: by a passport and by a version manifest, with overlapping fields and no rule establishing which one was authoritative. Second, the fact-origin model grew to five sources, a separate evidence entity, an array of references, and a revision graph for every passport—more costly than beneficial for local knowledge about an environment.

At the same time, a safe write path is defined only for `HarnessBundle`, which must reference a `SetupVersion`. Therefore, the “install one MCP for me” scenario has no normative semantics, and each part of the system may interpret it differently.

Finally, the list of component kinds is open and differs across documents, guaranteeing divergence among the CLI, registry, setup compiler, and providers.

## Options

1. Remove passports from components and setups, retaining only manifests. This eliminates duplication but deprives the agent of a single point for understanding an object and contradicts the product goal.
2. Retain both entities and define their boundaries. Duplication remains, and the boundary must be maintained with every change.
3. Combine them: the passport becomes the sole description of an object and includes the identity fields of an immutable version.
4. Add a second provider contract for installing a single component outside a setup. This doubles the security surface for convenience.

## Decision

Option 3 is accepted for description, together with a single write path for installation.

**The passport is the sole description of an object.** Developers, projects, components, and setups have passports. For a component and a setup, the immutable-version passport includes identity fields: the exact source, artifact hash, dependencies, conflicts, managed paths, permissions, license, and evidence references. There is no separate “version manifest” entity.

**Fact origin is simplified.** A fact stores a value, source, source reference, and observation time. The `inferred` source is removed because it is indistinguishable in practice. A separate evidence entity and the `evidence_refs` array in the passport are not used.

The list of sources in this record is refined in `ADR-0021-fact-origin-and-confirmation.md`: `confirmed` proved not to be a source, so origin and confirmation are separated into two independent axes. The other decisions in this record remain in force.

An exact hash, detailed verification reports, and signed attestations remain mandatory for a component version, setup version, bundle, verification report, and installation plan. The simplification concerns only local knowledge about an environment, not integrity evidence.

**The list of component kinds is closed.** The values and classification rule belong to `contracts/component-setup-passports.md`; changing the list requires a new ADR. The first such change was `ADR-0015-marketplace-as-provider-projection.md`, which removed `marketplace` from the taxonomy.

**Component dependencies are divided** into `requires_components`—exact references to component versions—and `requires_capabilities`—environment and project requirements from a closed vocabulary.

**Single write path.** Every change to a harness target materializes into a setup version, then into a bundle, then into a plan and provider application. Installing a component outside a setup is unsupported: the add command selects an existing setup or explicitly creates a personal one, adds the exact component version to the graph, performs conflict, permission, and transformation checks, creates a new setup version, and shows the plan before application.

**Attestations remain in the bundle.** The `attestations/` directory is retained: the separation of evidence sources under `ADR-0007` depends on it.

## Consequences

- `contracts/passport-envelope.md` describes the envelope for four passport kinds, not only for mutable local passports;
- the description of version passports moves to `docs/contracts/component-setup-passports.md`; no separate document about manifests remains because there is no separate version-manifest entity;
- a separate `setup-passport.json` is removed from the bundle structure only if the version passport is transmitted inside `bundle.json`; otherwise, the filename is retained;
- the schema gains closed enumerations for component kinds and the capability vocabulary, as well as a contract test for their completeness;
- the machine-readable CLI help declares actions for reading, drafting, adding, removing, updating, and installing a component, indicating that each passes through a setup version;
- an existing native configuration without a registered setup is first formalized as a personal setup, and this is a separate explicit step;
- `SPEC-003`, `SPEC-005`, `SPEC-006`, `SPEC-008`, and `SPEC-011` are aligned with this model together with the contracts and user flows.

## Reconsideration conditions

The decision shall be reconsidered if a proven scenario emerges in which materialization into a setup makes installation impossible or unsafe, or if the closed list of component kinds systematically fails to cover the native surfaces of supported harnesses.
