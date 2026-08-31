---
description: "Exact setup dependency closure: node, deterministic order, closed failure list, and resource limits."
last_verified: "2026-08-08"
---

# Setup dependency closure

The requirements owner is `SPEC-006` REQ-605, REQ-607, and REQ-608; the exact
reference form belongs to `canonical-data.md`, and the dependency passport belongs to
`component-setup-passports.md`. This document defines the closure's machine boundary:
what constitutes a node, the order in which nodes are returned, the available failures,
and the limits on graph size.

Closure builds and writes nothing. It answers one question: which exact versions are
required for the composition to be complete, and why no answer exists when it does not.
Package assembly belongs to `harness-bundle.md`.

## Node

A node is one exact version of one object:

```text
stable_id + version + passport_digest
```

All three are required. A reference without an exact version or digest is floating and
is rejected before any other checks: two machines resolving such a reference at
different times would assemble different compositions from one input, making `REQ-607`
unachievable.

A node also carries the held revision's `revision_id` and its depth—the shortest
distance from the root. Depth is descriptive and does not affect ordering.

## Ordering

The order is topological: a dependency precedes the object that requires it. Within
one layer, ascending `stable_id` defines the order, making it total and identical on
every machine. An order leaving ties unresolved would depend on dictionary insertion
order.

Roots are sorted by the same rule before traversal, so permuting input roots changes
neither the order nor the result digest.

## Failures

The list is closed. Each failure has a stable code that does not change with message
text and names the participating objects.

| Code | When it occurs |
|---|---|
| `reference_floating` | the reference does not name an exact version or digest |
| `dependency_missing` | the exact version in the reference is absent on this machine |
| `digest_mismatch` | the held version points to different content |
| `version_conflict` | two paths require different versions of one object |
| `dependency_cycle` | a cycle of required dependencies |
| `dependency_not_registrable` | the closure contains a draft or deleted object |
| `dependency_unreadable` | the dependency passport cannot be read as a version passport |
| `closure_too_deep` | a chain exceeds the resource limit |
| `closure_too_large` | the number of nodes exceeds the resource limit |

`dependency_missing` and `digest_mismatch` are intentionally distinct. The first means
the object is absent and must be obtained; the second means an object is present but is
not the expected one, indicating substitution or version-number republication. A shared
code would hide the second behind the first.

`version_conflict` is not resolved by selecting the "newer" version: `REQ-626`
prohibits automatic resolution of a semantic conflict, and selecting a version for the
user is exactly that. The conflict blocks closure, and a human decides through another
composition or an explicit derived version.

A failure is response data, not an execution error. An unresolvable closure is a normal
result explaining what is missing.

## Resource limits

`SPEC-006` requires bounding graph size. Limits are declared and returned in the
response, so a result that reaches a limit is distinguishable from a complete result:

```text
maximum depth: 32
maximum node count: 512
```

A limit is not a preference: a closure that reaches it is rejected, not truncated.
A truncated closure presented as complete is the worst possible failure because it
looks like success from the outside.

## No partial response

A closure is either fully resolved or unresolved. A response containing some nodes
alongside failures would read as "almost assembled," while a composition missing a
dependency is not assembled at all.
