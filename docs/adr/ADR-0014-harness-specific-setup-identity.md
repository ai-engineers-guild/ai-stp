---
description: "Decision to bind a setup to one harness and remove the setup variant from its identity."
last_verified: "2026-08-04"
---

# ADR-0014: A setup belongs to one harness

Status: accepted.

## Context

The previous model described a setup as a stable logical entity with a separate `SetupVariant` for each harness and immutable versions within each variant. The variant identifier was included in the exact reference alongside the stable identifier and version.

This created three problems. An exact reference mixed two different axes: which object it was and which native implementation it used. One logical version could mean different content in different environments, so version immutability ceased to be a property of the version itself. The provider boundary was also blurred: a bundle is always built for exactly one harness, but the object's identity implied that the version existed independently of it.

At the same time, `ADR-0012` had already removed the separate version-manifest entity, but the canonical contract continued to use `manifest_digest`, the `ai-stp:manifest:v1` hash domain, and a setup-level `variant_id`. Starting phase 1 with this model is dangerous: schemas, identifiers, and hash domains are fixed publicly and later require migration.

## Options

1. Retain `SetupVariant` as a separate identity entity. This preserves the current documents but fixes a mixed reference and ambiguous version immutability in the public schema.
2. Make a setup a cross-harness entity with a common version and variants within it. This reflects the user's view of a single project configuration but forces the common version number to change when one variant changes and leaves the variant within the version identity.
3. Make a setup belong to exactly one harness from the moment it is created.

## Decision

Option 3 is accepted.

**A setup is bound to one harness.** `harness_id` is set at creation and does not change. The `claude-developer` and `codex-developer` setups are two different setups, not variants of one.

```text
Setup
├── stable_id
├── harness_id        one harness, set at creation
├── owner_id
└── SetupVersion[]
     ├── version X.Y
     ├── passport_digest
     ├── exact references to component versions
     └── references to the artifact and bundle
```

**The separate setup-variant entity is removed.** `SetupVariant` and the setup-level `variant_id` field do not exist. An exact setup-version reference contains the stable identifier, version, and passport hash.

**Separation by harness is a goal, not an overhead.** Harnesses differ in capabilities, specifics, and native formats. A common version for two environments would promise an equivalence that does not exist: the same composition change is expressed differently in each, and some surfaces of one environment are simply absent from the other. A separate setup per harness makes this distinction visible instead of hiding it inside a common version number.

**There is no variant reconciliation mechanism in the MVP.** The product does not reconcile two related setups into a common state and does not promise that they remain synchronized. The user maintains them separately; composition divergence is visible through ordinary comparison of each setup's versions.

**Provenance is expressed by a relationship, not by identity.** A setup may reference another setup through optional `ported_from` and `related_setup_ids` fields. Such a relationship describes provenance and affinity but does not create a common version, common number, or common access right.

**The component variant is retained.** A component genuinely has different native implementations, so an exact component-version reference contains an optional `variant_id`. It denotes the component's native implementation, not a separate axis of setup identity.

**A project pins one setup per harness.** For every harness it uses, a project pins exactly one setup and exactly one active version. Previous versions are retained only for comparison and rollback. `production` and `experimental` channels and multiple simultaneously active versions of one setup are not supported in the MVP.

**The number of components is unlimited.** There is no product limit on the number of instructions, skills, MCPs, hooks, and other components within a setup. Limits arise only from conflicts, compatibility, and resources.

**The hash domain and field name are aligned with the passport.** A version is described by its passport, so `passport_digest` and the `ai-stp:passport:v1` domain are used. The word “manifest” is retained only for the limited file table inside a bundle and does not denote an identity entity.

## Consequences

- `contracts/canonical-data.md` describes an exact reference without a setup-level `variant_id`, with `passport_digest`, and without the `ai-stp:manifest:v1` domain;
- `contracts/component-setup-passports.md` and `contracts/passport-envelope.md` describe a setup-version passport with one `harness_id` and no variant;
- `architecture/domain-model.md` removes `SetupVariant` and adds a provenance relationship between setups;
- `SPEC-005` and `SPEC-015` no longer require a variant in a stored reference;
- a user who needs one configuration in two environments maintains two setups; the product shows their relationship but does not reconcile their state or promise synchronization;
- porting a setup to another harness is performed by creating a new setup with `ported_from`, not by adding a variant.

## Reconsideration conditions

The decision shall be reconsidered if maintaining two related setups proves more costly in practice than a common version and users begin systematically losing synchronization between environments, or if a provider emerges that requires a single cross-harness version for installation.
