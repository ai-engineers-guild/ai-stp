---
description: "Machine contract for passport-first inventory of one explicit authoring root."
last_verified: "2026-09-05"
---

# Path inventory

## Boundary

The requirements owner is `SPEC-005` REQ-534, REQ-535, and REQ-518. The
decisions are `ADR-0157` and `ADR-0158`. Native harness layouts remain
[native-component-discovery.md](native-component-discovery.md).

`component inventory --root` observes one named directory and writes nothing.
It does not scan global harness homes, does not mint a `stable_id`, and does
not register, adopt, or publish. `component discover --root` is the native
subset of the same scope: project layouts only.

## Classification

Canonical markers are read first: `setup-passport.json`,
`component-passport.json`, and `.ai-stp-template.json` with `setup.json`.
Native detectors then run on paths not already covered by those trees.

| `relation` | Meaning |
|---|---|
| `independent` | A logical component or setup rooted in the named tree |
| `embedded_member` | A component under a setup's `components/` |
| `generated_projection` | `projections/<harness>/` derived from `source/` |
| `duplicate` | The same declared name and kind as an earlier independent |

A generated projection directory is not an independent source even when it
looks like a portable skill. Pointing `--root` at that directory reports
`generated_projection` for `.` and does not walk the parent in as a second
object.

Malformed passport bytes are `invalid_manifest` diagnostics, not fabricated
settings. `stable_id` is present only when the passport already carries one;
this inventory never allocates one.

## Completeness

`complete` is false when a directory bound fires or a directory cannot be
listed. `continuation` is an opaque cursor of the remaining walk relative to
the named root. Passing it as `--cursor` with the same `--root` returns the
next disjoint page. Unreadable listings are `unreadable` diagnostics, not
empty results.
