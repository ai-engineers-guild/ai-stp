---
description: "Decision to treat the closed harness set as the MVP set and define platform promotion of a new harness from undefined."
last_verified: "2026-08-24"
---

# ADR-0033: Closed MVP set; promotion from undefined is a platform process

Status: accepted. Partially supersedes `ADR-0003`: the statement about the product's target count.

*Clarification dated 2026-08-24: `ADR-0120` changed the set's composition—seven harnesses are supported. The promotion process from this decision remains: a new official `harness_id` still requires an ADR, a schema version, and evidence, not publication of a user adapter.*

## Context

`ADR-0003` limited the MVP to five harnesses and introduced constrained `undefined`. This works: the enumeration is closed, `undefined` remains an observation under `SPEC-011` REQ-1109, and apply is impossible. But its consequences were stated more strongly than necessary: "five is the product's target count, not a temporary MVP boundary: the list is not planned to expand."

A permanent ceiling creates a trap. When a sixth harness appears with a verified detector, public provider, and recorded end-to-end evidence, documentation would force a choice between permanent `undefined` for a fully ready integration and retroactive violation of an accepted decision. Neither is managed evolution.

The opposite extreme—allowing users to publish their own adapters as official support—dilutes trust: an official `harness_id` promises a provider, release evidence, and platform matrix that a third-party adapter lacks.

## Options

1. Keep the permanent ceiling. Manageable today, a trap tomorrow.
2. Open publication of user adapters as official support. Fast expansion, but official status ceases to guarantee anything.
3. Treat five harnesses as the complete MVP set and make a new official `harness_id` a platform promotion process with its own evidence.

## Decision

Option 3 is accepted.

**Five harnesses are the complete MVP support set,** not a permanent product limit. This decision supersedes `ADR-0003`'s statement about the product's target count; the remainder of `ADR-0003`—closed enumeration, `undefined` as observation, and the shared protocol of five providers—remains effective.

**`undefined` remains observation only.** An unknown harness and its native configurations are recorded so users can see what they have; no setup, target, variant, provider, or adaptation draft is created, and apply returns `AI_STP_UNSUPPORTED_APPLY`.

**A new official `harness_id` appears only through the platform process:**

```text
1. verify external facts against the real harness
2. new ADR and versioned enumeration and schema change
3. public provider and trust in its releases
4. discovery fixtures and capability contract
5. bundle, plan, apply, status, and restore conformance
6. platform and guardrail checks and a recorded end-to-end run
7. initial beta-support status
```

**User adapters are not published as official support in the MVP.** Enumeration expansion follows `docs/engineering/schema-evolution.md`: an old client receives a typed incompatibility for an unknown value, not corrupted state.

## Consequences

- `ADR-0003` receives a reference to this decision and retains its original text as history;
- `SPEC-001` records that the closed set is the MVP set and closes the path for publishing a user adapter as official support;
- the set changed after this decision: `ADR-0120` expanded it to seven. The next composition change again starts with a new ADR and schema version;
- future promotion proceeds as cross-repository work in the established order.

## Reconsideration conditions

This decision will be reconsidered if the promotion process proves impassable for a real ready candidate—in that case process steps will be simplified rather than bypassed—or if a justified official-support model for third-party adapters appears with its own evidence.
