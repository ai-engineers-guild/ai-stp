---
description: "JSON envelope, error classes, and CLI machine-output rules."
last_verified: "2026-09-01"
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
  "next_actions": []
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
  "next_actions": []
}
```

## Output

In machine mode, standard output contains exactly one JSON object followed by a
newline. Colors, control sequences, and additional text are prohibited. The
error stream is used only for a failure before the envelope is constructed and
contains no secrets.

A warning does not change `ok` when the requested result was obtained in full.
A partially completed mutating operation returns an error and `operation_id`
rather than being masked as a warning.

Each element of `next_actions` is a command of this CLI, runnable as written
with `--json` and carrying every option the command requires. A value the
caller must supply stands in angle brackets; `...` stands for the caller's own
invocation, to be repeated with the options written beside it. A report never
answers with state names or prose in that field.

## Exit codes

| Code | Class |
|---:|---|
| 0 | Success. |
| 2 | Invalid input or schema. |
| 3 | Authentication, authorization, or device revocation. |
| 4 | Conflict, stale plan, or required user decision. |
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
defines the `exactly_one` and `required_when` relationships between parameters.
The special `present` value in `when_values` means that the parameter is present
regardless of its value. `summary` fields are not parsed as a contract. A
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
`plan_digest` → `install apply`; for `backup` and `rollback`, specifying
`--setup` or `--proposal` is unnecessary because these operations are bound to
the target and backup, not to the setup graph.
Thus, a web/desktop/agent consumer does not extract flags, enums, or action order
from Russian or English prose.
