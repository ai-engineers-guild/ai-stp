---
description: "SPEC-080: Headless CLI application services, capability inventory, and the agent task contract."
last_verified: "2026-09-15"
---

# SPEC-080: CLI agent task contract

## Purpose

Give the coding agent one headless application core: Click stays a parser,
expert commands and the task engine call the same in-process services, and
every declared leaf is classified so everyday journeys are not trapped behind
an expert-only vocabulary.

## Scope

Includes the application-service boundary, the inspect/task/expert inventory of
every declared command, the declared `task` lifecycle, and the rule that the
task engine must not reach another command through a nested process. Envelope
truth for unmet mutating goals is owned by `SPEC-011` `REQ-1132` and
`SPEC-058` `REQ-5809`; this specification names that those services are the
shared owner.

The first declared intent is `inspect`. It drains `doctor` and `capabilities`
through `application.inspect`. Installation through this surface, website
initialization prompt, persistent harness instruction attachment,
B2B/enterprise surfaces, estate-release F10/R05, a CLI language rewrite, and a
PyPI CLI cut are excluded.

## Terms

- `application service` — an in-process function that performs one domain
  effect or inspection. Handlers and the task engine call it. It does not parse
  argv and does not start another CLI process to reach another service.
- `inspect` — a cheap orientation command. Reading it does not mutate a
  target, journal, or account. Creating a durable task may create the local
  registry so the task can be stored.
- `task` — an everyday journey the task engine drains, or the engine's own
  lifecycle commands. Everyday journeys remain callable expert-shaped leaves
  until an intent owns them.
- `expert` — a leaf that stays a leaf: diagnosis, grants, evaluation, and
  other exceptional control. Everyday journeys must not live only here.
- `task engine` — `task start`, `answer`, `continue`, `status`, and `cancel`.
  It persists a `task_…` object, is idempotent on start, and continues by
  matching revision. There is no machine-global current task.

## Requirements

- `REQ-8001`: Domain work shared by expert commands and the task engine lives
  in in-process application services. Click remains a parser (`ADR-0057`). A
  service does not start another CLI process to reach another service.
- `REQ-8002`: Every declared leaf is classified exactly once as `inspect`,
  `task`, or `expert`. The inventory test is the oracle. The `task` class is
  non-empty and includes the everyday install, registry, target, and adopt
  journeys plus the five lifecycle commands.
- `REQ-8003`: Paths `task start`, `task answer`, `task continue`, `task
  status`, and `task cancel` are declared and run. Their result schema is
  `cli-task`.
- `REQ-8004`: Expert commands remain for diagnosis and exceptional control.
  They call the same application services the task engine calls. Duplicated
  business logic beside a service is refused.
- `REQ-8005`: A task object uses the `task_…` identifier prefix. Envelope
  `operation_id` remains an `operation_…` receipt or null. Multi-root
  transaction ids already minted as `operation_…` under `SPEC-058` stay that
  prefix.
- `REQ-8006`: Intent `inspect` drains `application.inspect.doctor` and
  `application.inspect.capabilities`. Expert `doctor` and `capabilities`
  return the same models as those functions at the same moment. Completing
  inspect satisfies the task goal even when the doctor report is not `ready`.
- `REQ-8007`: `task start` is idempotent on the pair of `idempotency-key` and
  intent payload. `continue`, `answer`, and `cancel` require the current
  revision. Status names the task id; the process does not hold a current
  task. A successful `task status` may describe a failed, cancelled, or
  compensated target.
- `REQ-8008`: Advancing a task calls named application services for that
  intent. It does not look up an arbitrary expert leaf in the command
  registry and run it.

## States and errors

Task `state` is distinct from envelope `ok`. `planned` means the task exists
and can be continued. `completed` means this intent finished; inspect stores
the doctor report and capabilities in `outcome`. `cancelled` is a settled
abandonment. Unmet mutating goals on expert install paths remain `CliFailure`
per `REQ-1132`.

Unknown intent, missing task, and revision mismatch are registered failures
(`AI_STP_VALIDATION_ERROR`, `AI_STP_NOT_FOUND`, `AI_STP_CONFLICT`). Inspect
has no questions; `task answer` is refused.

## Security and privacy

Application services inherit the secret, path, and privilege rules of the
commands they serve. A service does not read a TTY prompt or a secret from
ordinary task JSON. Untrusted catalog or file text cannot become an executable
authority grant.

## Compatibility and migration

Existing expert command paths remain. Registry descriptor `next_actions` may
narrow to scoped `help --path` orientation without removing a command. Envelope
`continuations` stay additive inside major 1. Local registry schema 42 adds
`agent_task`; the reverse drops that table.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-8001` | Import graph and unit tests: `ai_stp_cli.application` has no nested-process tokens; `capabilities` and `doctor` are served from that layer. |
| `REQ-8002` | `test_cli_capability_map` classifies every declared path; everyday install/registry/target/adopt paths and the five lifecycle paths are `task`. |
| `REQ-8003` | The same test asserts the five `task` lifecycle paths are declared. |
| `REQ-8004` | Expert handlers `capabilities` and `doctor` call application services rather than duplicating their bodies. |
| `REQ-8005` | Compensated and verified multi-root envelopes carry `operation_…` receipts; a started inspect task mints `task_…` in the payload, not as envelope `operation_id`. |
| `REQ-8006` | `test_cli_task` continues inspect and compares `outcome` to `application.inspect` at the same moment. |
| `REQ-8007` | The same tests cover idempotent start, revision conflict, cancel, and status by id. |
| `REQ-8008` | `application/task.py` does not import the command registry or resolve handlers by path. |
