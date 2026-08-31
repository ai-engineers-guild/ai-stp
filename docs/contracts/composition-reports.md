---
description: "Composition and conversion reports: closed conflict classes, permitted compiler operations, and loss states."
last_verified: "2026-08-28"
---

# Composition and conversion reports

The requirements owner is `SPEC-006` REQ-606, REQ-609, REQ-625, and REQ-626;
`ADR-0028` defines the MVP compiler boundary. Dependency closure belongs to
`setup-graph.md`, and the package belongs to `harness-bundle.md`. This document
defines the machine boundary of the two reports: which conflicts exist, which compiler
operations are permitted, and how incomplete conversion is described.

Reports explain and do not modify. They are not a reasoning mechanism and do not edit
the composition: `REQ-609` requires them, while `SPEC-006` explicitly states that they
remain deterministic explanations.

## Conflict classes

The list is closed and covers what `SPEC-006` enumerates for the compiler. The four
closure classes—cycle, missing reference, hash mismatch, and incompatible versions—
belong to `setup-graph.md` and are not repeated here: the composition is not assembled
until closure is resolved.

| Code | When it occurs |
|---|---|
| `managed_path_owned_twice` | one managed path is claimed by two components, including a nested path under another owner's root |
| `native_id_collision` | the same native command, agent, MCP, or plugin identifier |
| `instruction_precedence_conflict` | two instructions require the same precedence level |
| `hook_order_conflict` | two hooks require the same order for the same event |
| `native_surface_lost` | a required native surface is absent from the target harness |
| `path_escapes_bundle` | a path is absolute, parent-relative, or escapes the package |
| `managed_path_outside_projection` | a managed path is not under the projection root for its type |
| `undeclared_environment` | an environment variable or external endpoint is required but not declared by the composition |
| `permission_escalation` | the composition requires permission beyond what the target allows |
| `redistribution_forbidden` | the composition is intended for redistribution but a component prohibits it |
| `entitlement_missing` | a required entitlement has not been granted |
| `unverified_without_consent` | the composition contains an `experimental` trust-line candidate without consent |
| `unsupported_platform` | the system, architecture, and harness combination is unsupported |

A semantic conflict blocks the package and is not merged automatically. `REQ-626`
prohibits automatic semantic merging, equivalent selection, and composition optimization;
resolution belongs to the user through another component, an explicit derived version,
or an overlay, and the derived object passes checks as a separate exact version.

## Permitted operations

`REQ-625` restricts the MVP compiler to deterministic operations. The list is closed,
and the composition report lists only operations applied from it:

```text
canonical_ordering
exact_reference_deduplication
dependency_closure
disjoint_managed_path_union
deterministic_report_generation
```

No operation outside the list exists. Managed paths are combined only when disjoint:
an overlap is the conflict above, not an operation. An exact repeated reference is
collapsed: the second copy of one `stable_id` and `X.Y` is rejected with a stable reason
rather than selected twice. A declared path is a root, not an exact file string:
`skills/foo` covers `skills/foo/SKILL.md`, and two such claims belong to one owner.
The `hooks.json` manifest additionally owns the adjacent `hooks/` directory: handlers
next to the file are the same surface, not a second owner.

## Composition report

The composition report names what was selected, what was rejected, and the reason for
each decision:

- a selected component—exact reference, trust line, and reason for inclusion;
- a rejected candidate—exact reference and stable rejection reason;
- applied operations—only from the list above;
- detected conflicts—using the codes above.

The report is stable: identical canonical input produces the same entry order. Ascending
identifier defines the order, so ties are never left unresolved.

## Conversion report

The conversion report states what each component becomes in the target harness and
what is lost. Entry state:

| State | Meaning |
|---|---|
| `complete` | the target harness has a native surface for this type |
| `partial` | a surface exists, but some declared content is not transferred |
| `unsupported` | the harness has no native surface for this type |

`unsupported` is not itself an error: the component may be optional. A required
component without a surface produces `native_surface_lost` and blocks the package under
`REQ-608`.

Losses are named individually. A report with a "losses exist" field but no list explains
nothing, while `REQ-609` specifically requires a loss-aware report.

## Empty composition

A composition without components exists through an explicit emptiness indicator
(`REQ-630`, `ADR-0124`). Its composition report names zero selected components and zero
conflicts: this is managed emptiness, not a missing report. A confirmed empty
`SetupVersion` is immutable and installed through the provider's normal plan. A file
appearing in the target is drift, not the same thing as uninstalling.
