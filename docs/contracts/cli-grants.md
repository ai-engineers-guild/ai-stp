---
description: "Client sequence for issuing, accepting, and revoking access grants."
last_verified: "2026-10-13"
---

# CLI access-grant flow

The `grant` commands are a thin authorized client for the wire models from
`packages/contracts`. Grant scope and revocation consequences belong to
[access-grants-and-forks.md](access-grants-and-forks.md); the CLI does not
calculate permissions or replace the server response with a local guess.

`grant invite` and `grant direct` address an exact `component` or `setup`, its
stable identifier, and its major line. `grant list` rereads server state after
creation, acceptance, or revocation. Every mutating command requires `--confirm`
and a stable caller-supplied `--idempotency-key`: the same key denotes the same
intended effect and is preserved across transport retries.

`grant revoke` also requires `--expected-revision` from the reviewed `grant list`
result. Reissuing a revoked direct grant requires both `--expected-grant-id` and
`--expected-revision`, with a new idempotency key for the new intent. The CLI
never fetches or refreshes these preconditions automatically. A stale revision
fails without changing access; read the current grant before deciding again.

Direct and revoke receipts bind the actor, key, and exact request. Reusing a key
for different input fails. Replaying a completed direct request returns the
grant's current state, including any later revocation. Replaying a completed
revoke returns its original outcome without revoking a later regrant; use
`grant list` to observe current state.

Older API responses without a revision remain readable but cannot authorize a
mutation. Older CLI builds cannot supply these new preconditions: update the
CLI before revoking or reissuing access. The API refuses unbound requests,
including old retries for which no receipt was retained before this upgrade.
The database also rejects state changes from older API writers that do not
advance the revision. Rollback must retain this protection and use a compatible
writer; reverting application code alone does not restore old mutation behavior.

`grant accept` obtains the invitation secret only from the environment variable
named by `--token-env`. The token value is not a process argument and does not
appear in a URL, machine help, output, or error message. Creation and list
responses also do not contain the raw invitation token.

Revoking an invitation and revoking an active grant are separate commands. They
do not delete already obtained local bytes; current state is confirmed through
`grant list`. All commands require an active cloud session and use the common
HTTPS endpoint check without redirecting the bearer token to another authority.
