---
description: "CLI machine help as the source of available commands and schemas."
last_verified: "2026-09-20"
---

# Machine help

Machine help is how the Agent learns which commands exist and how to invoke them. The Skill neither rewrites nor guesses the flag list: `SPEC-011` REQ-1106 explicitly forbids this.

## Two Entry Points

```text
ai-stp task intents --json
```

Durable agent journeys start here. Do not type `ai-stp capabilities` or
`ai-stp help --agent` as the first move: both dump every command path,
including `install plan`.

Expert orientation (not the everyday start):

```text
ai-stp capabilities --json
ai-stp help --agent --json
```

They answer different questions and intentionally do not replace each other.

`capabilities` answers **what this installation can do right now**: versions,
whether this process loaded a published wheel or this checkout, the local
registry schema it reads, the command-registry fingerprint, supported harnesses,
whether catalog and synchronization are enabled, and a command-path list as a
pointer. The payload keeps `command_paths` (SPEC-080 REQ-8006). Inspect
orientation does not copy that list.

`help --agent` answers **which commands, fields, and errors exist**. It is the full
registry: for each command, it provides the path, purpose, mutability class,
confirmation rule, parameters, result schema, and family-orientation next actions; for
each error code, it provides the exit class, a brief meaning, and initial Agent
`handling`. The response is considerably larger. An unknown `--path` lists
`task intents` instead of dumping that registry. An unscoped dump still carries
a `task intents` continuation so the everyday catalog is the next argv.
`help --find <text>` keeps only the commands whose path or summary mentions the
text — inside the `--path` scope when both are given — so a caller that does not
know the family name reaches the same descriptors without the full dump.

`schema list` and `schema show --id <name|urn|file>` answer **what shape a
payload or task input has**: every `result_schema` and `input_schema` URN the
CLI emits resolves through them at runtime to the same JSON Schema the
`schemas/v1` gate publishes. `schema list --find <text>` keeps only the names
containing the text; a `schema show` miss names the closest ids in
`details.candidates`. A bare `schema` or an invented `schema` verb steers to
`schema list`. A `task intents` descriptor also carries
`input_fields`, the flat name/required/choices list derived from the same
validation model, so choosing an intent and shaping `--input` take one call.
`--input` itself accepts a JSON or YAML object with duplicate keys refused; a
validation refusal names the rejected fields and carries `details.errors` —
`{pointer, issue, detail}` entries in the RFC 9457 `errors[]` shape, never the
rejected values — and continues to the matching `schema show` argv.

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

Durable agent journeys start at `task intents --json`, then `task start`,
`task answer`, `task continue`, `task status`, `task cancel`, and `task
list`. The five lifecycle verbs keep result schema `cli-task`; `task list`
reads `cli-task-list` and answers the unsettled durable tasks — id, revision,
intent, state, binding context and open question ids — most recently touched
first, so a caller that lost its reference resumes instead of starting a
second task on a bound target. Compact discovery is
`cli-task-intents`. `help --agent` remains the full registry. Shipped intents
are `inspect`, `initialize`, `install`, `change`, `author`, `switch`,
`account`, and `publish`. Inspect stores doctor plus slim
orientation (no `command_paths`). Unshipped intent names are refused. There is no
stored current-task pointer. `task answer --json` or `task continue --json`
without `--task` emits that unique blocked human question's answer argv when
exactly one unsettled task exists, and the `task list` argv when several are
open; the same verbs with `--task` and without
`--revision` emit that named task's answer argv. With none unsettled they list
`task intents`. The continuation still names `--task` and `--revision`.
`task start --json` without `--intent`, and `task start --intent` with a
name that is not shipped, list `task intents` and do not echo Click's
missing-option or choice dump. A shipped intent without the key emits
the start argv with `<intent>-session-01`.
An incomplete command group that a shipped intent already drains
(`install`, `auth`, `publication`, `sync`, `setup compose`, `setup preserve`,
`setup restore`, `setup preserved`) returns `task start` for that intent.
Other incomplete groups return `task intents --json`. The envelope does not
list expert leaves. A `task_covered` leaf that fails Click parse, or a bare
handler validation such as `install plan --json`, is the same `task start`
as its group. Everyday pending leaves (`setup compose plan`,
`select propose`, `component adopt`, `component discover`) do the same. `install plan --action
backup|rollback` and `auth login` with
a supported `--provider` plus another flag stay leaf errors.
`sync preview` stays a leaf error.
A scoped `help --path install` dump carries the install start continuation,
not an empty one. Mixed families (`component`, `select`, `setup`,
`registry`, `config`) list `task intents`. `help --path doctor` carries none.
A successful `task_pending` everyday leaf (`component discover --json`)
carries the same draining start continuation.

## What Enters the Registry

A command appears in machine help only when it works. A declared but unimplemented command is worse than an absent one: the Skill would plan around a step that cannot be performed.

The mutability class (`read`, `plan`, `apply`, `destructive`) and confirmation rule (`none`, `explicit_flag`, `plan_digest`) are declared on each command. `plan_digest` is a machine binding of exact bytes, not a person. `explicit_flag` is only the remaining stops in `interaction-policy.md`. The value vocabulary belongs to `packages/contracts`.

The CLI does not prompt in the terminal. A decision arrives through an explicit flag or the exact digest of a stored plan; its absence yields `needs_user_action`, not an input prompt. This keeps the execution path identical for people and agents and prevents hangs in CI or containers.

Registry `next_actions` on a descriptor are orientation toward a command
family (`help --path … --json`). They are not copied onto a success envelope.
Executable next steps come from handler `continuations`.

A process exit class is not an Agent action. For example, class `4` groups a
conflict, a stale plan, a request for a decision, and a compensated mutation.
The Agent matches the exact `error.code` to `error_codes`, then considers the
specific response's `handling`, `retryable`, and `continuations`. After a
timeout without a confirmed effect, it first checks the status/recovery
surface and does not blindly repeat a mutating call.

## Why It Works This Way

The Skill uses this contract, so updating the CLI does not require manually rewriting five large instructions.
