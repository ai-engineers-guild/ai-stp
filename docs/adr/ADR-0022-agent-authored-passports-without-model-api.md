---
description: "Decision to leave passport creation to the user's agent and not call a model from ai_stp."
last_verified: "2026-08-29"
---

# ADR-0022: The agent assembles passports; `ai_stp` does not call a model

Status: accepted. The server-side presentation projection is clarified by `ADR-0131`.

## Context

Product documents stated that the system automatically creates a developer passport and extracts project facts. The wording did not distinguish two roles: what the deterministic CLI does and what the user's already-running coding agent does.

This leads to an incorrect implementation. The phrase "the system creates a passport" permits a model call inside `ai_stp`, and therefore a separate model key, a separate bill, a separate network dependency, and a separate surface for context leakage. This contradicts both the product premise that the user's agent is the primary consumer and the promise of full local operation without an account.

## Options

1. Keep the wording and decide during implementation. Cheap now, but the choice will be made silently and discovered after a model dependency appears.
2. Embed a model call in `ai_stp`. Provides independence from the agent, but requires a key and billing, breaks local mode, and duplicates what the user's agent can already do.
3. Explicitly establish the separation of roles and prohibit first-party model calls in the MVP.

## Decision

Option 3 is accepted.

**`ai_stp` does not call model interfaces.** The MVP does not require or store a model key and contains no model client. The absence of a key does not degrade any product function.

**Roles are separated.**

```text
CLI      deterministically discovers facts and findings,
         validates, stores, and versions the passport

Agent    interprets findings, asks the user questions,
         completes the passport and selects the composition

User     confirms unknown and disputed information
```

**The loop is machine-readable.** The agent performs discovery, retrieves facts and findings, asks questions, assembles the passport, validates it, and registers it. Every step is available as a command with machine output, so the agent does not guess parameters.

**The CLI does not present a decision as the agent's.** Deterministic constraints, schema, conflicts, and permissions are checked mechanically, but composition choices and wording remain with the agent and the user.

**Unknown remains unknown.** The CLI does not substitute a guess for an undiscovered fact: it returns an honest absence of value and the reason.

## Consequences

- `docs/product/vision.md`, `feature-list.md`, and `user-flows.md` describe the agent's role rather than autonomous passport creation by the system;
- `SPEC-003` and `SPEC-011` establish the discovery, validation, and registration loop without a model call;
- `docs/engineering/dependency-policy.md` and `tech-stack.md` do not include a model client among MVP dependencies;
- a dependency check rejects the appearance of a model client or a key requirement;
- adding an optional first-party model call in the future requires a new decision.

## Reconsideration conditions

This decision is reconsidered if a function emerges that the user's agent cannot perform through a machine contract and its value outweighs the cost of a key, billing, and a new network dependency.
