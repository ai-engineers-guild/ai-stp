---
description: "Click remains a parser; in-process application services own effects; envelope ok means the requested effect completed."
last_verified: "2026-09-16"
---

# ADR-0181: Application services own CLI effects

Status: accepted.

## Context

The primary consumer of the CLI is the user's coding agent. Today's surface is a
large registry of expert-shaped leaves. An agent that must choreograph
plan/approve/apply/observe as separate tool calls invents commands, treats
compensation as success, and copies static `next_actions` that are not valid
argv.

`ADR-0057` already keeps Click a thin parser. Issue #261 authorizes extracting a
headless application core so a later task engine and the retained expert
commands share one implementation. Recursive subprocess calls to `ai-stp` would
duplicate parsing, lose in-process transactions, and teach the agent to drive
the product through a shell.

A multi-root install that rolled back every child used to return `Answer` with
`ok: true`. Restoration succeeded; the requested install did not. Envelope `ok`
must mean the requested effect completed.

## Options

1. Keep handlers as the only orchestration. Agents continue to chain expert
   commands. This preserves today's vocabulary and keeps every journey
   model-choreographed.
2. Add a task facade that shells out to `ai-stp` for each inner step. This
   duplicates the parser and cannot share a SQLite transaction.
3. Extract in-process application services. Click handlers and the task
   engine call the same functions. Envelope `ok` is reserved for a completed
   request; compensation and partial mutation are registered failures. Descriptor
   `next_actions` become scoped help, not copied mutation argv.

## Decision

Option 3 is selected.

`apps/cli/src/ai_stp_cli/application/` owns in-process inspect, task, install,
change, author, switch, inventory, catalog acquire, publication, auth, sync,
select/compile, and outcome helpers. Expert command modules call them. The task
engine calls the same functions for declared intents. Nothing in that layer
imports `ai_stp_cli.commands` or starts another CLI process. Provider protocol
may use `subprocess`; a nested `ai-stp` process is refused.

Click remains the argv parser (`ADR-0057`). It does not decide envelope `ok`,
error codes, or exit class.

`ok` on a machine envelope means the requested effect completed.
`AI_STP_COMPENSATED` (exit class 4, `reconcile_state`, HTTP 409) is a finished
compensation of a mutation that did not complete. `AI_STP_PARTIAL_OPERATION`
remains the recovery-required case. That mapping applies to multi-root
apply/recover and to single-root `install apply` / `install resume`.
Diagnostic `doctor` stays `ok` with check results in the payload, because the
request was inspection. Completing an `inspect` task is the same: envelope
`ok` with a doctor report that may not be `ready`. Inspect outcome stores
slim orientation, not the full `command_paths` dump. Completing `initialize`
with the antigravity limitation is also success: the catalog has no global
instruction file to write. `TaskView.outcome` is discriminated on `kind` so a
later intent cannot be parsed as inspect.

Executable next steps are handler `continuations`. Each continuation carries
JSON argument values, executable `argv`, and `actor`. `continuation_command`
is quoted display for humans and older callers and is never eval input. A
terminal outcome emits no continuation. Machine-help descriptor
`next_actions` are orientation toward `help --path <family> --json` and are
not copied onto success envelopes as if they were bound argv.

Task identifiers use the `task_` prefix. Envelope `operation_id` remains an
`operation_…` receipt or null. Existing multi-root transaction ids remain
`operation_…` because `SPEC-058` already mints them that way. Compact
discovery is `task intents`. The schema enum grows only when an intent is
drained. Drained intents are `inspect`, `initialize`, `install`, `change`,
`author`, `switch`, `account`, and `publish`.
`initialize` patches
the catalogued user-global instruction surface through the optional provider
region operation. Production looks up the remembered chosen or configured
provider only — never PATH discovery, never `ensure_provider`. Until that
provider declares `patch_instruction_region` **and** `instruction_section`
the task stays blocked (`setup-systems#316` still has to declare both).
`antigravity` records the catalog limitation instead of inventing a file.
When drain kwargs are omitted, a non-empty test hook on
`provider_operations` still selects `patch_via_provider`; otherwise drain
reads bound provider-info. Isolation refusals stay typed failures.
`install` drains plan, task-authority approve, and apply in-process.
`change` mints a new setup identity with lineage to the source, then installs
that pin; it does not edit a saved setup in place. `author` registers one
directory as one embedded component and one setup identity; it does not install
and does not mutate a saved setup. `switch` restores the last user working
config via `preserved_setup`, captures drift as a leftover, and blocks on
`reload-session`; it never kills the caller and never claims the session loaded.
`account` drains device-code login, logout, and explicit sync; login never
uploads. `publish` drains the no-binding publication plan with filesystem
provenance; a worker receipt is not a readable catalog result. `task continue`
claims the current revision (`running`) before effects so two continues on the
same revision have one winner. An install continue records the child operation
after plan; a later continue of that task resumes instead of planning again.
Remaining intents are later verticals; the engine does not run arbitrary expert
leaves.

## Consequences

- `SPEC-080` owns the service boundary, capability inventory, and declared task
  lifecycle. `SPEC-011` `REQ-1132` and `SPEC-058` `REQ-5809` own envelope mapping.
- Everyday journeys stay callable as expert-shaped leaves until an intent owns
  them. They are classified `task_pending` (or `task_covered` once drained) so
  they cannot hide in the expert set. Expert rows carry a one-line reason.
  `TaskView.outcome` is a `kind`-discriminated union so a second intent cannot
  be parsed as inspect.
- A second continuation protocol beside `Continuation` is refused.
- HTTP status for `AI_STP_COMPENSATED` follows exit class 4 as 409.

## Revisit conditions

Revisit when a second runtime must consume the same service boundary without
Python imports, when installation must drain through `task` without remaining
expert leaves, or when descriptor `next_actions` must carry bound argv again
without becoming a second continuation channel.
