---
description: "CLI machine help as the source of available commands and schemas."
last_verified: "2026-09-05"
---

# Machine help

Machine help is how the Agent learns which commands exist and how to invoke them. The Skill neither rewrites nor guesses the flag list: `SPEC-011` REQ-1106 explicitly forbids this.

## Two Entry Points

```text
ai-stp capabilities --json
ai-stp help --agent --json
```

They answer different questions and intentionally do not replace each other.

`capabilities` answers **what this installation can do right now**: versions, supported harnesses, whether catalog and synchronization are enabled, and a command-path list as a pointer. It is an inexpensive first call.

`help --agent` answers **which commands, fields, and errors exist**. It is the full
registry: for each command, it provides the path, purpose, mutability class,
confirmation rule, parameters, result schema, and reasonable next actions; for
each error code, it provides the exit class, a brief meaning, and initial Agent
`handling`. The response is considerably larger.

Both responses are assembled from the same registry in `apps/cli`, so they cannot disagree about which commands exist.

## Owners

| Fact | Owner |
|---|---|
| Machine-help shape: fields, enumerations, schemas | `packages/contracts` and `schemas/v1` |
| List of existing commands and their parameters | registry in `apps/cli` |
| Envelope, error codes, `handling`, and exit codes | closed registry in `packages/foundation` and `docs/contracts/cli-json.md` |
| Requirements and acceptance criteria | `SPEC-011` |

The machine-help shape is declared with the wire models rather than inside the application that prints it: five harness projections depend on it, so it is a machine boundary of the same kind as `/v1`. Each command with a payload publishes its exact schema URN in `result_schema`; the corresponding files are generated in `schemas/v1`, so no manual schema list is maintained here.

The command list belongs to the registry and grows with implemented tasks. It is not duplicated here: a copy in this document would diverge from the implementation on the first change, while the Skill reads the implementation.

## What Enters the Registry

A command appears in machine help only when it works. A declared but unimplemented command is worse than an absent one: the Skill would plan around a step that cannot be performed.

The mutability class (`read`, `plan`, `apply`, `destructive`) and confirmation rule (`none`, `explicit_flag`, `plan_digest`) are declared on each command. `plan_digest` is a machine binding of exact bytes, not a person. `explicit_flag` is only the remaining stops in `interaction-policy.md`. The value vocabulary belongs to `packages/contracts`.

The CLI does not prompt in the terminal. A decision arrives through an explicit flag or the exact digest of a stored plan; its absence yields `needs_user_action`, not an input prompt. This keeps the execution path identical for people and agents and prevents hangs in CI or containers.

A process exit class is not an Agent action. For example, class `4` groups a
conflict, a stale plan, and a request for a decision. The Agent matches the exact
`error.code` to `error_codes`, then considers the specific response's `handling`,
`retryable`, and `next_actions`. After a timeout with no confirmed effect, it first
checks the status/recovery surface and does not blindly repeat a mutating call.

## Why It Works This Way

The Skill uses this contract, so updating the CLI does not require manually rewriting five large instructions.
