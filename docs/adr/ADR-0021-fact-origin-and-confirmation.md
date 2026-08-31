---
description: "Decision to separate fact origin from user confirmation."
last_verified: "2026-08-04"
---

# ADR-0021: Fact origin and confirmation are two axes

Status: accepted. Clarifies `ADR-0012` with respect to fact origin.

## Context

`ADR-0012` simplified the fact model to one source field with four mutually exclusive values: `declared`, `observed`, `confirmed`, and `imported`. The simplification was directionally correct: a five-value model with a separate evidence entity and a revision graph for every passport cost more than it provided.

But one of the four values proved not to be a source. `confirmed` answers "did the user confirm it?", while the other three answer "where did the value come from?" As a result, a normal scenario loses data: the analyzer observed `Python 3.12`, the agent showed the value to the user, and the user confirmed it—so the fact must cease to be observed because there is only one field.

The consequences extend beyond wording. A repeated scan cannot know whether it may update a value the user once confirmed. A sync merge cannot distinguish a user-confirmed value from a declared one. An explanation of a component choice cannot state what the fact is based on.

## Options

1. Keep one field. Changes nothing, but loses either origin or confirmation as soon as an observation is confirmed.
2. Restore the full evidence model with a separate entity and a reference graph. Restores precision, but also restores the cost that `ADR-0012` deliberately removed.
3. Split the one field into two independent axes and keep the rest of the model lightweight.

## Decision

Option 3 is accepted.

**A fact has two independent axes.**

```text
value
origin: declared | observed | derived | imported
confirmation: none | user_confirmed
source_refs: bounded list
confidence: optional
observed_at: optional
confirmed_at: optional
```

**`confirmed` ceases to be an origin.** User confirmation is recorded on the second axis and does not erase origin.

**`derived` is added.** A value computed from other facts by a deterministic rule differs from direct observation. This does not restore the removed `inferred`: `derived` requires a recorded rule and references to source facts, rather than a model confidence estimate.

**Source references are a bounded list.** One value may have multiple sources, but the list is length-limited and does not become an evidence graph.

**Confirmation is reset when an observation changes materially.** If a repeated observation produces a different value, `confirmation` returns to `none`, and the discrepancy is shown to the user. Silently retaining confirmation for the new value is prohibited.

**The model remains lightweight.** Exact hashes, verification reports, signed confirmations, and installation plans are unaffected: they remain mandatory and immutable and are not mixed with the origin of environment facts.

## Consequences

- `contracts/passport-envelope.md` describes the two axes, `derived`, and the confirmation reset rule;
- `SPEC-003` changes the origin requirement and gains an executable check for the transition from observed to confirmed;
- `ADR-0012` remains in force in all other respects and refers here for origin;
- sync merging considers both axes and does not lose confirmation when independent fields are merged;
- a recommendation trace can refer to fact origin without a separate evidence entity.

## Reconsideration conditions

This decision is reconsidered if a scenario requires multiple independent confirmations of one fact by different participants, or if `derived` begins to be used to bypass an honest low-confidence `observed` value.
