---
description: "Decision that bounded component discovery reports completeness and a resumable cursor."
last_verified: "2026-09-05"
---

# ADR-0158: Bounded discovery returns completeness and a continuation

Status: accepted.

## Context

Portable-skill and path-inventory walks have finite directory budgets. Hitting
the budget emitted `bounded_limit` and stopped. `NativeComponents` had no
`complete` flag and no cursor, so an agent could treat a truncated listing as
exhaustive. `except OSError: continue` made an unreadable directory look empty.
`_shape_of` already distinguished `unreadable` from `absent`; the walk did not.

Project discovery (`SPEC-004`) already has `complete` without a cursor. That
command tells the agent to narrow the root. Component discovery needs a
partition the agent can resume without changing the named root.

## Options

1. Keep diagnostics only. Agents keep guessing whether the list is complete.
2. Add `complete` without a cursor, as project discovery does. The agent must
   invent a narrower root, which is not a partition of the same walk.
3. Return `complete` and an opaque continuation of the remaining DFS stack.
   `--cursor` is declared only with a handler that resumes that stack.

## Decision

Option 3. Pages are disjoint. Their union equals one adequately provisioned
scan. Unreadable listings are `unreadable` diagnostics and `complete=false`.
A continuation is relative to the named `--root` and carries no home path.

## Consequences

- `component discover --root` and `component inventory --root` accept `--cursor`.
- Machine help names `--cursor` because the handler reads it.
- Global discovery without `--root` has no continuation.

## Revisit conditions

A budget-increase flag is added, or continuation is required for global homes.
