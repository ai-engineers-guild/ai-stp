# Envelope

Every `--json` command prints exactly one object.

With `ok: true`, the result is in `data`. `warnings` may be shown without making
the call unsuccessful. With `ok: false`, `error.code` is a stable code from the
closed registry, and `next_actions` names a sensible next step.

Find `error.code` in `error_codes` from machine help and follow its `handling`,
together with the response's `retryable` and `next_actions`. Do not choose an
action from the process exit class alone: one class can include a conflict, a
stale plan, or a request for a user decision.

Retry only when `retryable: true`. After an unconfirmed timeout, first check the
actual effect through the proposed status or recovery command.

`next_actions` is an ordered hint, not permission. Before every next call, read
its descriptor again.
