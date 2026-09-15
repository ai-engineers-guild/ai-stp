---
description: "Click remains a parser; in-process application services own effects; envelope ok means the requested effect completed."
last_verified: "2026-09-15"
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
3. Extract in-process application services. Click handlers and a later task
   dispatcher call the same functions. Envelope `ok` is reserved for a completed
   request; compensation and partial mutation are registered failures. Descriptor
   `next_actions` become scoped help, not copied mutation argv.

## Decision

Option 3 is selected.

`apps/cli/src/ai_stp_cli/application/` owns in-process inspect and outcome
helpers. Expert command modules call them. A later `task` dispatcher calls the
same functions. Nothing in that layer spawns `ai-stp`.

Click remains the argv parser (`ADR-0057`). It does not decide envelope `ok`,
error codes, or exit class.

`ok` on a machine envelope means the requested effect completed.
`AI_STP_COMPENSATED` (exit class 4, `reconcile_state`, HTTP 409) is a finished
compensation of a mutation that did not complete. `AI_STP_PARTIAL_OPERATION`
remains the recovery-required case. Diagnostic `doctor` stays `ok` with check
results in the payload, because the request was inspection.

Executable next steps are handler `continuations`. Machine-help descriptor
`next_actions` are orientation toward `help --path <family> --json` and are not
copied onto success envelopes as if they were bound argv.

Task identifiers, when introduced, use a prefix other than `operation_`.
Existing multi-root transaction ids remain `operation_…` because `SPEC-058`
already mints them that way.

## Consequences

- `SPEC-080` owns the service boundary, capability inventory, and reserved task
  paths. `SPEC-011` `REQ-1132` and `SPEC-058` `REQ-5809` own envelope mapping.
- Everyday journeys stay callable as expert-shaped leaves until the task engine
  lands. They are classified `task` so they cannot hide in the expert set.
- A second continuation protocol beside `Continuation` is refused.
- HTTP status for `AI_STP_COMPENSATED` follows exit class 4 as 409.

## Revisit conditions

Revisit when the task engine needs a durable `task_…` identifier on the
envelope, when a second runtime must consume the same service boundary without
Python imports, or when descriptor `next_actions` must carry bound argv again
without becoming a second continuation channel.
