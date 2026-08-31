---
description: "Decision to limit the MVP setup compiler to deterministic operations without semantic merging while retaining an extensible graph."
last_verified: "2026-08-04"
---

# ADR-0028: Simple deterministic MVP setup compiler

Status: accepted.

## Context

`SPEC-006` describes a setup compiler over an arbitrary dependency graph: overlays, conflict classes, composition reports, and transformations. The model is valid as an extensible foundation but does not separate the data representation from the scope of the first implementation. A reader may interpret the contract as requiring the MVP to resolve the graph semantically: automatically merge conflicting instructions, select equivalent components, and optimize the composition.

That interpretation is dangerous in two ways. It inflates the first implementation beyond manageable scope and opens the door to nondeterministic transformations that cannot be reproduced or verified. The proposal in issue #46 correctly identifies the risk but addresses it by removing the graph model, contrary to the accepted product direction.

## Options

1. A full semantic compiler in the MVP. Maximum automation, but irreproducible transformations, an enormous surface, and delayed end-to-end product validation.
2. A flat compiler without a graph, as proposed in issue #46. Small and simple, but discards the exact dependencies, overlays, and reports already accepted as the model's foundation.
3. Retain the extensible exact graph, but explicitly limit the MVP compiler to a closed set of deterministic operations and a blocking conflict list.

## Decision

Option 3 is accepted.

**`SetupGraph` remains the exact dependency representation.** Nodes, exact references, overlays with `derived_from`, and reports remain unchanged.

**The MVP setup compiler permits only deterministic operations:**

- canonical ordering of nodes and records;
- deduplication of identical exact references;
- resolution of the exact dependency closure;
- merging of non-overlapping managed paths;
- deterministic generation of reports and package bytes.

**The setup compiler is prohibited from semantic conflict resolution.** It does not automatically merge conflicting instructions, hooks, commands, MCPs, agents, plugins, or settings, select an equivalent, or optimize the composition. A semantic conflict blocks the package; selecting another component or creating an explicit derived component or overlay belongs to the agent and user, and the derived object becomes a separate exact version subject to the same checks.

**Blocking conflicts are a closed list.** A cycle or missing exact reference, hash mismatch, two owners of one managed path, duplicate native identifier of a command, hook, MCP, agent, or plugin, incompatible versions of one component, unsupported native surface, a path or reference escaping the package, a license or access violation, undeclared mandatory environment or external endpoint, authority expansion without confirmation, an `experimental` candidate without consent, an unsupported OS and harness pair, and provider `validate-bundle` or `plan-bundle` rejection.

**Reports remain reports.** `CompositionReport` and `ConversionReport` are deterministic explanations of composition and loss, not reasoning mechanisms.

## Consequences

- `SPEC-006` receives requirements for permitted operations and the prohibition on semantic merging;
- the blocking-conflict boundaries gain the missing classes;
- issue #46 is partially incorporated: the implementation boundary is accepted, while removal of the graph model is rejected;
- graph resource and build-time limits are measured during implementation phases and are not invented in this decision.

## Reconsideration conditions

This decision will be reconsidered after end-to-end MVP validation if real cases accumulate where a documented deterministic transformation rule can demonstrably replace manual selection safely. Such rules will be added one at a time with their own checks, not as general "smart merging."
