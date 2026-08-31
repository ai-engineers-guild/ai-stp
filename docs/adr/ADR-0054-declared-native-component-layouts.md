---
description: "Declarative native layouts for five harnesses and reproducible discovery candidate identity."
last_verified: "2026-08-09"
---

# ADR-0054: Declarative Native Component Layouts

Status: accepted.
Amended by `ADR-0106`: a declared key within the settings file proves the client MCP.

## Context

Native component discovery covered Claude Code and part of Codex, although the MVP
declares five harnesses. Traversing unknown directories would be broader than the
explicit contract and would inevitably classify user files by guesswork.
At the same time, a single path may be compatible with multiple harnesses, so
duplicating one finding under multiple `harness_id` values would make subsequent
adoption by path ambiguous.

Codex, Pi, OpenCode, and Grok Build also support relocatable roots and shared
`.agents` directories. The harness root cannot be derived from the product name or
replaced with a common convention.

## Decision

The CLI contains a closed table of layout rules. Each rule declares the component
type, path form, scope, owning harness, and a link to the official documentation.
A global path is constructed either from the documented harness config root,
including its environment override, or from home for the shared `.agents`
convention. Project rules are constructed only from an explicitly supplied project
root.

A shared path is emitted once with `harness_id=null`, rather than copied for all
compatible consumers. The result has `layout_source` and `candidate_id`.
`candidate_id` is a domain hash of the canonical set of `component_type`,
`harness_id`, `scope`, the redacted `source_path`, and `layout_source` in the
`ai-stp:native-discovery:v1` domain. It is stable for a single finding and is not
the persistent logical `Component.stable_id`: the latter appears only after an
explicit `component adopt`.

Discovery reads only directory entries and file metadata, sorts the complete
result deterministically, does not open file contents, and writes nothing. A new
harness or a new layout is added only together with an official source and an
executable fixture.

## Consequences

- Claude Code, Codex, Pi, OpenCode, and Grok Build have verifiable global and
  project coverage without scanning home;
- `PI_CODING_AGENT_DIR`, `OPENCODE_CONFIG_DIR`, `GROK_HOME`, and `CODEX_HOME`
  control survey and component discovery identically;
- an agent can reference a stable `candidate_id` and show the provenance of the
  classification, but still passes the exact path for adoption;
- package, marketplace, and GitHub provenance is not inferred from the location
  on disk and requires a separate source adapter;
- compatible paths are not attributed to an arbitrary harness.

## Reconsideration Conditions

The decision is reconsidered if an official harness makes an incompatible layout
change, a versioned layout manifest appears, or there is a need to address one
physical finding through multiple independent variants without ambiguous adoption.
