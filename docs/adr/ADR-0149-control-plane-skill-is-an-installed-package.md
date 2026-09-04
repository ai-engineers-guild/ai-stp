---
description: "Decision that the control-plane Skill is installed as a portable package whose harness projections carry the procedure."
last_verified: "2026-09-04"
---

# ADR-0149: The control-plane Skill is an installed package

Status: accepted.

## Context

`SPEC-011` requires one canonical Skill with native projections for every
supported harness. The generator wrote thin wrappers that pointed at
`skills/canonical/ai-stp/SKILL.md`. That path exists in a checkout and not on a
user's machine, so `skill install --harness` delivered a pointer, not a
procedure. Tests required the pointer. Issue `#97` named this as the remaining
CLI operating gap.

Copying flags into the Skill would violate `REQ-1106`. Keeping the pointer
violates the product's primary consumer: the agent that installed the wheel.

## Options

**Keep pointer projections.** No procedure ships. Rejected.

**Copy the command list into every projection.** Drifts from machine help.
Rejected by `REQ-1106`.

**Install a portable package:** one map plus `references/` playbooks; a harness
projection is that procedure with `metadata.harness` and a short native-surface
note; argv still comes from machine help. Costs a delivery and test inversion.

## Decision

The installed control-plane artefact is a package: `SKILL.md`, `references/`,
and `.ai-stp-skill.json` covering every owned file. A harness projection carries
the same procedure. It must not name a repository path as a runtime location.
English is the executed canonical source; Russian is a generated locale
projection of the same map and playbooks. `--target` stays required until
`SPEC-014`.

## Consequences

- `SkillDelivery` reports the package digest and owned relative paths.
- Contract tests scan every file in the package, not only `SKILL.md`.
- Tests that forbade a projection from carrying `## Hard rules` invert.
- Removing a user setup still must not delete this Skill (`REQ-1107`).

## Revisit conditions

Harness skill-directory discovery (`SPEC-014`) would allow a default
destination. A measured need for a third locale would extend the generator
matrix, not a second hand-written procedure.
