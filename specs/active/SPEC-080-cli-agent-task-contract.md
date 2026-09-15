---
description: "SPEC-080: Headless CLI application services, capability inventory, and the reserved agent task contract."
last_verified: "2026-09-15"
---

# SPEC-080: CLI agent task contract

## Purpose

Give the coding agent one headless application core: Click stays a parser,
expert commands and a later task engine call the same in-process services, and
every declared leaf is classified so everyday journeys are not trapped behind
an expert-only vocabulary.

## Scope

Includes the application-service boundary, the inspect/task/expert inventory of
every declared command, reserved `task` lifecycle paths, and the rule that a
later task dispatcher must not shell out to `ai-stp`. Envelope truth for
unmet mutating goals is owned by `SPEC-011` `REQ-1132` and `SPEC-058`
`REQ-5809`; this specification names that those services are the shared owner.

Excluded: implementing `task start|answer|continue|status|cancel` (later
increment), website initialization prompt, persistent harness instruction
attachment, B2B/enterprise surfaces, estate-release F10/R05, a CLI language
rewrite, and a PyPI CLI cut.

## Terms

- `application service` — an in-process function that performs one domain
  effect or inspection. Handlers and a later task dispatcher call it. It does
  not parse argv and does not spawn `ai-stp`.
- `inspect` — a cheap orientation command. Reading it does not mutate a
  target, journal, or account.
- `task` — an everyday journey the future task engine will drain. Today these
  remain callable expert-shaped leaves.
- `expert` — a leaf that stays a leaf: diagnosis, grants, evaluation, and
  other exceptional control. Everyday journeys must not live only here.
- `task engine` — the reserved dispatcher for `task start`, `answer`,
  `continue`, `status`, and `cancel`. It is specified here and not declared in
  the command registry until it can run.

## Requirements

- `REQ-8001`: Domain work shared by expert commands and the task engine lives
  in in-process application services. Click remains a parser (`ADR-0057`). A
  service does not spawn `ai-stp` to reach another service.
- `REQ-8002`: Every declared leaf is classified exactly once as `inspect`,
  `task`, or `expert`. The inventory test is the oracle. The `task` class is
  non-empty and includes the everyday install, registry, target, and adopt
  journeys.
- `REQ-8003`: Paths `task start`, `task answer`, `task continue`, `task
  status`, and `task cancel` are reserved and absent from the registry until
  each can run. Guessing them is an unknown command, not an empty payload.
- `REQ-8004`: Expert commands remain for diagnosis and exceptional control.
  They call the same application services the task engine will call. Duplicated
  business logic beside a service is refused.
- `REQ-8005`: A later task object uses its own identifier prefix. Envelope
  `operation_id` remains an `operation_…` receipt. Multi-root transaction ids
  already minted as `operation_…` under `SPEC-058` stay that prefix; they are
  not rewritten into a second type in this increment.

## States and errors

Declared expert and inspect commands keep their existing journal and envelope
states. Unmet mutating goals are `CliFailure` per `REQ-1132`. Reserved `task`
paths are not declared, so they produce the ordinary unknown-command failure
rather than a task-shaped envelope.

When the engine lands, task states are distinct from call success: a successful
`task status` may describe a failed or compensated target. That representation
is not shipped in this increment.

## Security and privacy

Application services inherit the secret, path, and privilege rules of the
commands they serve. A service does not read a TTY prompt or a secret from
ordinary task JSON. Untrusted catalog or file text cannot become an executable
authority grant.

## Compatibility and migration

Existing expert command paths remain. Registry descriptor `next_actions` may
narrow to scoped `help --path` orientation without removing a command. Envelope
`continuations` stay additive inside major 1. Introducing `task_…` identifiers
later is additive; it does not reuse `operation_…` for tasks.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-8001` | Import graph and unit tests: `ai_stp_cli.application` has no subprocess to `ai-stp`; `capabilities` is served from that layer. |
| `REQ-8002` | `test_cli_capability_map` classifies every declared path; everyday install/registry/target/adopt paths are `task`. |
| `REQ-8003` | The same test asserts the five `task` lifecycle paths are disjoint from `DECLARATIONS`. |
| `REQ-8004` | Expert handlers such as `capabilities` call application services rather than duplicating their bodies. |
| `REQ-8005` | Compensated and verified multi-root envelopes carry `operation_…` receipts; no `task_…` prefix is minted. |
