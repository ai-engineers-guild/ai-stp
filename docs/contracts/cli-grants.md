---
description: "Client sequence for issuing, accepting, and revoking access grants."
last_verified: "2026-08-13"
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

`grant accept` obtains the invitation secret only from the environment variable
named by `--token-env`. The token value is not a process argument and does not
appear in a URL, machine help, output, or error message. Creation and list
responses also do not contain the raw invitation token.

Revoking an invitation and revoking an active grant are separate commands. They
do not delete already obtained local bytes; current state is confirmed through
`grant list`. All commands require an active cloud session and use the common
HTTPS endpoint check without redirecting the bearer token to another authority.
