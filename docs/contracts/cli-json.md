---
description: "JSON envelope, error classes, and CLI machine-output rules."
last_verified: "2026-09-16"
---

# JSON CLI

## Success

```json
{
  "schema_version": 1,
  "ok": true,
  "request_id": "request_...",
  "operation_id": null,
  "data": {},
  "warnings": [],
  "next_actions": [],
  "continuations": []
}
```

## Error

```json
{
  "schema_version": 1,
  "ok": false,
  "request_id": "request_...",
  "operation_id": null,
  "error": {
    "code": "AI_STP_VALIDATION_ERROR",
    "message": "Safe message",
    "retryable": false,
    "details": {}
  },
  "next_actions": [],
  "continuations": []
}
```

A parse failure on a declared command names every required option the call
lacks in `error.details.options` (in declared order, with the `--` prefix), and
its continuation is an `inspect` step to `help --path "<command path>" --json`.
An agent therefore repairs the call in one retry rather than meeting one
refusal per flag. The same leaf-scoped continuation answers other parse
failures on a declared command — an unknown option or an invalid value — while
commands covered by a task intent still answer with that intent's start, and an
unknown command or bare group still answers with the intent catalog.

## Output

In machine mode, standard output contains exactly one JSON object followed by a
newline. Colors, control sequences, and additional text are prohibited. The
error stream is used only for a failure before the envelope is constructed and
contains no secrets.

In human mode the same facts are plain text: each warning prints as a
`warning:` line before the payload, and each distinct `next_actions` or
`continuations` command prints once as a `next:` line after it, so the second
phase of a two-command flow is named rather than discovered by trial.

`ok` is true only when the requested effect completed. A warning does not
change `ok` when that result was obtained in full. A partial or compensated
mutating operation returns an error and `operation_id` rather than being
masked as a warning or as a successful payload that names `rolled_back`.
Diagnostic `doctor` remains `ok` with check results in the payload: the
request was inspection. Completing `task continue` for intent `inspect` is
the same: envelope `ok`, `data.task_id` is a `task_…` identifier, and
`operation_id` stays null. A doctor report that is not `ready` does not make
the task call a failure.

`doctor` reports diagnostic results without applying registry migrations. Its
`local_registry` check is `ready` when an existing readable registry only needs
a supported automatic migration; `detail` names the current and target schema.
This condition does not require a user decision. An unreadable registry or a
schema newer than the installed reader remains `failed`.

Each element of `next_actions` is a command of this CLI, shown as a quoted
display of executable tokens, with `--json` and carrying every option the
command requires. A value the caller must supply stands in angle brackets.
Unresolved steps are not written as argv with `...`: they are
`help --path <family> --json` when `argv` is empty, or they live in
`continuations` with a non-empty `missing` list. Explicit `argv` is kept
even when `missing` is non-empty. A blocked human continuation binds
`task answer` without the missing value. A report never answers with state names or prose
in that field. `next_actions` is never passed to a shell.

`continuations` is additive inside major 1. An older producer omits the field;
a reader treats absence as an empty list. Each item names a declared command
`path`, JSON arguments already bound, executable `argv`, `actor`, and
`missing` for names the caller must still supply. `argv` is derived from
the declared parameters: a boolean binds as a bare flag, a valued option
as `--name value` (or `--name=value` when the value begins with a dash),
and a repeatable option once per element. `argv` and `actor` are
additive on the continuation object. `next_actions` remains the quoted
display of `argv` for older callers. A finished compensation emits no
continuation.

## Exit codes

| Code | Class |
|---:|---|
| 0 | Success. |
| 2 | Invalid input or schema. |
| 3 | Authentication, authorization, or device revocation. |
| 4 | Conflict, stale plan, required user decision, or compensated mutation. |
| 5 | Unavailable dependency or timeout without a confirmed effect. |
| 6 | Partial operation requiring recovery. |
| 70 | Unexpected internal error. |

The class is useful to the process wrapper but does not determine the agent's
sole action. The exact `handling` for each stable `AI_STP_*` code is published
in `help --agent --json`. A conflict and a request for a user decision may have
the same exit class and different actions. A retry is allowed only when the
specific envelope reports `retryable: true`; a timeout without a confirmed
effect requires first checking the status or recovery path from `next_actions`.

## Compatibility

Unknown optional fields are allowed within a supported major version. An
unknown major version is rejected. The `code` field is a stable machine
identifier; the human-readable message may be refined without changing behavior.

## Integration without parsing text

An integration first reads `help --agent --json`, selects a command by its exact
`commands[].path`, and builds argv from `parameters`: `required` defines whether
a parameter is mandatory, `value_type` defines the value form, `repeatable`
defines repeatability, `choices` is a closed vocabulary, and `parameter_rules`
defines the `exactly_one`, `at_most_one`, `required_when` and `forbidden_when`
relationships between parameters.
A rule carrying `when_parameter` and `when_values` applies only while that
parameter takes one of those values; the special `present` value in
`when_values` means that the parameter is present regardless of its value, and
an empty `when_parameter` means the rule always applies. `summary` fields are
not parsed as a contract. A
successful response payload is validated against `result_schema`; a failure is
validated against the common error-envelope schema and the exact `error.code`
from `error_codes`.

Primary user intents already have unambiguous paths: search is
`registry search`; discovery and adoption are `component discover` and
`component adopt`; daily state and drift are `target status` and
`target diff`; selecting the previous verified version is `target rollback`.
Update is not a hidden separate command: the agent selects a new exact version,
obtains an `install plan` with `action=update`, and applies only the confirmed digest.

`target rollback` and `target backups` answer different questions, and the
distinction is normative. The former names the previous verified **version**
and restores nothing. The latter lists provider **backups** from which recovery
is possible: a backup reference is not setup identity (`REQ-814`), and combining
them in one response would erase the very boundary for which both requirements
exist. Recovery remains the standard sequence
`install plan --action rollback --backup-ref` → `install approve` with the exact
`plan_digest` → `install apply`; for `backup` and `rollback`, at most one of
`--setup` or `--proposal` may be named and neither is required, because these
operations bind to the target and backup, not to the setup graph (`REQ-1207`).
Thus, a web/desktop/agent consumer does not extract flags, enums, or action order
from Russian or English prose.
