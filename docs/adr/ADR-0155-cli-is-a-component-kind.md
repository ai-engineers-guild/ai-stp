---
description: "Decision to add `cli` as a ninth component kind, distinct from a slash `command`."
last_verified: "2026-09-05"
---

# ADR-0155: A standalone executable is kind `cli`, not a slash command

Status: accepted.

## Context

`ADR-0015` closed the component taxonomy at eight values after removing
`marketplace`. Those eight answer “what part of a setup is this?”. A standalone
executable that an agent discovers, registers, publishes, installs, and invokes
as a process is none of them. Authors were disguising such tools as `command`
(a named slash invocation), `skill` (a procedure the harness attaches), or
`setting` (a typed key). That made search by kind meaningless and made seven
harness copies of one binary look like seven adaptations.

`command` remains the named invocation surface (`/review`). Kind `cli` is a
shared process with one runtime artifact. Harness integration is process
execution and configuration, not seven native layouts.

## Options

1. Keep disguising executables as `command`, `skill`, or `setting`. Preserves
   the eight-value list and keeps inventing the wrong object.
2. Add a tenth packaging value under `projection_kind`. Packaging is how an
   object is delivered, not what it is.
3. Add `cli` as a ninth component kind. Portable by default. One shared
   artifact. `command` stays declarative.

## Decision

Option 3. The closed list is:

```text
instruction
skill
mcp
hook
command
agent
plugin
setting
cli
```

`cli` is executable. Authoring language is never `none`. The scaffold is
portable: a concrete harness variant is refused so the same binary is not
copied into seven layouts. `projection_kind` for the artifact is `package`.
`marketplace` remains packaging, never a kind.

`ADR-0015` is not rewritten. It remains the decision that removed
`marketplace` from the taxonomy. This record extends the list that decision
left.

## Consequences

- `ComponentType` in `packages/passports` is the one owner; derived lists
  read it.
- `SPEC-005` REQ-510 accepts nine values and still rejects `marketplace`.
- Postgres CHECK constraints, official-upstream allowlists, and catalog
  persistence consume the enum and need a platform migration (colleague
  zone). The CLI and shared contract change without that migration.
- Web presentation registry gains a `cli` icon and locales (`ADR-0074`).

## Revisit conditions

A supported harness whose only way to invoke an external process is a native
slash command with no process-execution surface, or a need to ship distinct
per-OS binaries as adaptations rather than as assets of one `cli` version.
