---
description: "Decision to treat a marketplace as a provider projection rather than a component kind."
last_verified: "2026-08-04"
---

# ADR-0015: Marketplace is a provider projection, not a component kind

Status: accepted.

## Context

`ADR-0012` closed the list of component kinds with nine values, including `marketplace`. The other eight values answer “what part of a setup is this?”: instruction, skill, MCP, hook, command, agent, plugin, or setting. The `marketplace` value answers a different question: “in which native packaging is this delivered to a specific harness?”

As a result, the same object received two incomparable descriptions. A plugin distributed through the native Grok Build marketplace could be recorded as either `plugin` or `marketplace`, making search by component kind meaningless as a filter. `AGENTS.md` already prohibited using `marketplace` as a general name for a setup, confirming that the term occupied the wrong place in the taxonomy.

The list is closed, and `ADR-0012` requires a new decision to change it. Narrowing the list changes the public schema just as extending it does, so it is recorded separately.

## Options

1. Retain `marketplace` as a component kind and define a classification rule. This preserves the schema but leaves two overlapping axes in one closed list and makes filtering by kind ambiguous.
2. Remove `marketplace` without replacing it. This eliminates the ambiguity but loses the ability to describe that an object is delivered through a harness's native marketplace.
3. Remove `marketplace` from the taxonomy and express packaging through a separate projection field.

## Decision

Option 3 is accepted.

**The list of component kinds contains exactly eight values.**

```text
instruction
skill
mcp
hook
command
agent
plugin
setting
```

**Packaging is described separately.** The native delivery form is expressed by a projection field with its own closed vocabulary:

```text
projection_kind: marketplace | plugin | native_files | package
```

The field belongs to provider and component-variant metadata, not to the component kind. A harness marketplace may contain plugins and components; it describes the delivery channel, not a catalog entity.

**Search uses two independent axes.** The `component_type` filter answers the question about an object's role in a setup; the `projection_kind` filter answers the question about native packaging. Combining them in one list is prohibited.

## Consequences

- `contracts/component-setup-passports.md` lists eight kinds and introduces `projection_kind`;
- `SPEC-005` changes the enumeration requirement from nine values to eight and gains a separate requirement for the projection vocabulary;
- `docs/agent/harness-projections.md` continues to describe the native Grok Build marketplace, but as a projection rather than a component kind;
- the contract check for the enumeration rejects `marketplace` in `component_type`;
- existing examples and fixtures that use nine values are updated together with the schema.

## Reconsideration conditions

The decision shall be reconsidered if a supported harness emerges whose marketplace is an independently installable unit with its own passport, dependencies, and versions rather than a delivery channel for other components.
