---
description: "Decision that an explicit path is a passport-first inventory and does not import global homes."
last_verified: "2026-09-05"
---

# ADR-0157: Explicit-path inventory is passport-first and scoped to the named root

Status: accepted.

## Context

`component discover --root` scanned declared global harness homes and the named
project together. An authoring tree with `component-passport.json` and
`projections/<harness>/` was invisible unless it happened to match a native
layout. Pointing at a generated projection that contained `SKILL.md` could
register that projection as an independent portable skill.

Adoption still has to find a global file by path: it infers a lookup root from
the file's parent and is not the path-inventory workflow.

## Options

1. Keep combining global homes with `--root`. Agents pointing at a tree keep
   importing unrelated configuration.
2. Stop scanning globals whenever any project path is set, including adoption
   lookup. Global `adopt --path ~/.codex/config.toml` then fails closed.
3. Make the path workflow (`component discover --root`, `component inventory
   --root`) skip global homes and read authoring passports first. Adoption
   lookup may still include globals.

## Decision

Option 3. `inventory_root` classifies `component-passport.json` /
`setup-passport.json` and `.ai-stp-template.json` before native detectors.
`projections/<harness>/` is `generated_projection`. Setup `components/` members
are `embedded_member`. No stable id is minted. `component discover` without
`--root` remains the explicit global mode.

## Consequences

- CLI tests hold mixed-tree classification, projection-not-independent, and no
  home bleed.
- Completeness cursors stay `A17`; this inventory reports `complete=false` when
  a walk bound fires and does not invent a resume token.
- Public provider `setup.json` without a passport remains identity-less
  (`ADR-0156`).

## Revisit conditions

Adoption grows an explicit `--root` that is not inferred from the file parent,
or A17 adds a resumable cursor to the same inventory.
