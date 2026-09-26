# Envelope

Every machine JSON command prints exactly one object.

With `ok: true`, the result is in `data`. `warnings` may be shown without making
the call unsuccessful. With `ok: false`, `error.code` is a stable code from the
closed registry, and `next_actions` names a sensible next step.

Find `error.code` in `error_codes` from machine help and follow its `handling`,
together with the response's `retryable` and `next_actions`. Do not choose an
action from the process exit class alone: one class can include a conflict, a
stale plan, or a request for a user decision.

Retry only when `retryable: true`. After an unconfirmed timeout, first check the
actual effect through the proposed status or recovery command.

`next_actions` is an ordered hint, not permission. Each entry is runnable argv
of this CLI. It never contains an ellipsis standing in for the previous call.
Unresolved values are angle-bracket placeholders, a scoped help read for that
command family, or a typed continuation whose `missing` list is non-empty.
A human continuation binds `task answer` without the missing value; do not
execute that argv.
`continuations[0].actor` is a JSON field (`cli`, `human`, or `external`), not
the user's identity. You are the coding agent: run `task intents` and
`task start` yourself. Execute continuation `argv` only when that field is
`cli`. When that field is `human`, do not execute the printed `argv` (the
value is missing on purpose); answer immediately from the conversation
through `task answer --task <id> --revision <n> --value <answer>`;
`--input` carries structured objects, not the agent's reply, and an answer
the task never consumed leaves it blocked. Waiting for a person is not the
job. `task start`
already advanced the task; do not insert `task continue` when `actor` is
`human` or when there are no continuations. When `actor` is `external`,
show the payload once; do not execute `argv`. `provider-too-old` is not
login. A device-code payload may later take `task continue` after the
browser; never poll.

`continuations` is additive: older builds omit it. When `ok` is false and
`error.details.state` is `failed`, the task is settled: empty `continuations`
means stop. Do not invent `task get`. Resolve the next call against
the cached descriptor for the installed version. Read a result schema only when
its fields are unclear. A corrected input or a freshly computed plan is a new
operation, not a blind retry of a permanent error. Honor server retry timing;
retain completed work while waiting.
