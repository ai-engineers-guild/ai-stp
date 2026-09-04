# Decisions

The user's task is the authority boundary. Local reversible steps inside that
task run without a fresh question.

`mutability` and `confirmation` are independent. `confirmation: none` is not consent.

- `read` — observe.
- `plan` — exact subject of a later decision.
- `apply` — when the current request already authorizes it.
- `destructive` — always a separate decision immediately before the call.

A separate user decision is required when: an unresolved choice changes the
result; visibility or access changes; a primary version line is created;
credentials or an account are linked; data, a target, or a backup is deleted
without recovery; an unrequested Git or deploy action is performed; or an
`experimental` or unverified-author object enters composition.

For `explicit_flag`, obtain the decision, then pass the parameter named by the
descriptor. For `plan_digest`, run the named plan command, show the effect and
`required_authorization`, then pass the digest the CLI returned. Do not compute
it. A stale plan means a new plan and a new decision if the effect changed.

Digest, precondition, and idempotency checks are mechanical, not questions.
