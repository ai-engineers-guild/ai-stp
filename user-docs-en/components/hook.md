---
description: "Hook components: automation on harness events."
---

# `hook`

A `hook` is an action bound to a harness event: before a command runs, after a
file changes, before an install, before a push, or at another supported moment
in the lifecycle.

A hook is useful when a check or a preparation has to happen automatically. It
is also the most sensitive component kind: a mistake in a hook can change state
without the user's direct attention.

## Where a hook fits

| Scenario | Why a hook |
| --- | --- |
| Check a passport before publishing | the event repeats and must be unavoidable |
| Refuse to apply without a backup | a guardrail belongs next to the lifecycle |
| Refresh a generated index before a docs build | it can be made reproducible |
| Remind the agent to read a document | usually better as an `instruction` |
| Install an unknown package | not suitable without separate confirmation |

## How it works in `ai_stp`

1. The passport describes the event, the action, the target and the limits.
2. The compiler checks whether the harness supports that lifecycle event.
3. The provider shows the plan for changing the hook configuration.
4. The user confirms the apply.
5. After applying, the hook must be visible in status and in the operation
   journal.

??? danger "Why a hook deserves extra attention"
    A hook can run while the user is thinking about something else. That is why
    preview, backup, a clear name and a quick way to switch it off matter more
    for `hook` than for anything else.

## A short checklist before enabling one

- the event is clear to a person;
- the action can be explained in one sentence;
- there is a way to disable or roll the hook back;
- there are no secrets in the passport;
- the provider plan changes no unexpected files;
- a beta harness does not need a manual step you skipped.
