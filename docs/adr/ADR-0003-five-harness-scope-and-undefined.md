---
description: "Decision to limit the MVP to five harnesses."
last_verified: "2026-08-24"
---

# ADR-0003: Limit the MVP to five harnesses

Accepted on 2026-08-03.
Partially superseded by `ADR-0033` for the MVP harness-set boundary and
promotion process.

## Context

The closed setup-system authoring circuit vendors far more harness applications as submodules than the MVP needs. An unbounded list would require a separate native converter, separate release evidence, and a separate platform matrix for every harness. At the same time, an unknown harness cannot simply be rejected: discovery and a passport remain useful without trusted installation.

## Decision

The MVP supports Claude Code, Codex, Pi, OpenCode, and Grok Build. Claude Code/Codex receive primary support; the others are beta. An unknown harness receives the ID `undefined` and a scan/passport/adaptation draft, but not trusted automatic apply.

## Consequences

Five is the product's target number, not a temporary MVP boundary: there are no plans to expand the list, and the remaining harnesses from the closed circuit are not included in the `ai_stp` distribution.

*Clarification on 2026-08-04: the first formulation of the paragraph above was superseded by `ADR-0033` — the closed set is the complete MVP set, and official promotion of a new harness from `undefined` is defined by the platform process. The rest of this decision remains in effect.*

*Clarification on 2026-08-24: the composition of the set was changed by `ADR-0120` — seven harnesses are supported. `undefined` and the closed nature of the enumeration from this decision remain in effect.*

Five providers implement one shared protocol rather than five local formats. The harness identifier becomes a closed enumeration of six values. Extending the list requires a new ADR, a new line of release evidence, and coordinated changes to five public repositories.

The boundary of the `undefined` path is clarified by `SPEC-011` REQ-1109: an unknown harness and its native configurations are recorded as an observation, no managed objects are created for it, and apply returns a distinct error code. The adaptation draft mentioned in the original formulation of the decision is cancelled: it promised an entity that nothing could apply.
