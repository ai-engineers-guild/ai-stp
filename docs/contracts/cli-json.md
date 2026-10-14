---
description: "JSON envelope, error classes, and CLI machine-output rules."
last_verified: "2026-10-14"
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

## Native output and handling

`apps/cli-v2/src/lib.rs`, `main.rs`, `error.rs` and the executable registry own
the current output behavior. Machine mode emits exactly one JSON envelope and
newline. Public command failures use the same envelope shape. Human mode prints
help or a formatted payload; a failure goes to stderr. Secrets are never echoed.

The native parser reports invalid invocation without reproducing input. Inspect
scoped machine help to obtain accepted parameters. Do not assume the Python
parser's per-option diagnostics or intent redirection exist in Rust.

Success means the requested service returned successfully. Inspect the returned
state and receipts before claiming installation or live authentication. In
particular, `doctor` is read-only metadata, account status is cached, and a plan
is not an applied effect. Production migration is always explicit.

`operation_id` is currently null in the outer native envelope; operation and
task identifiers are retained in their domain payloads. `next_actions` is empty.
Task continuations carry their own path, arguments, argv, actor and missing
facts. Execute argv only when actor is cli and the required facts are resolved.
Keep CLI task ids separate from execution-tool process handles. A stale revision
requires reading current task state, not inventing a replacement idempotency key.

## Exit codes

Read error codes and handling from `help --agent --json`. The native executable
and this table are compared by the release proof:

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 2 | Invalid input or object not found |
| 4 | Failed precondition or conflict |
| 5 | Dependency unavailable |
| 70 | Internal error |

Only dependency unavailability is marked retryable by the envelope renderer. Before retrying a
mutation after an uncertain transport result, inspect its retained status or
resume the original admitted plan.

The envelope stays major version 1 and is exercised against shared Python
consumer models. Those models also retain historical fields and error classes;
their presence in a shared schema does not advertise a native command or effect.
