---
description: "Client-side publication plan sequence and the boundary of transmitted data."
last_verified: "2026-08-25"
---

# CLI publication

`publication plan --id <stable_id> --version <X.Y>` builds a server-side plan for
an exact locally released component version. The command reads the revision stored
with that version, not the current draft head. It produces a public immutable
version passport; the wire format and server states belong to the `publication-*`
schemas in `packages/contracts`.

Creating a plan does not itself publish the object. The resulting `plan_id`,
`plan_hash`, `expires_at`, and effects must be reviewed, after which a separate
`publication confirm --plan-id <id> --plan-hash <hash> --confirm` command confirms
that exact snapshot. `publication status --plan-id <id>` is the read-only path for
verification and recovery if the confirm response is lost.

The creation request includes the passport and artifact digest. Source component
bytes, local paths, session tokens, and values of required credentials are not
added to the passport or machine output. The session token exists only in the
header of the authenticated HTTP call.

Each plan or confirm invocation creates an idempotency key once before the first
network request. Internal transport retries use the same request. Repeating the
confirm command after an indeterminate result is not a way to discover the
outcome: first read the status of the previously known plan.

## Setup publication

A setup cannot become public before its exact pins, so it is published not as a
separate plan but as a **set**. The
`setup publish plan --id <setup> --version <X.Y>` command creates one plan for
each pinned component that is not yet public and one for the setup itself. An
already public participant is listed and is not replanned. The decision is
`ADR-0114`; the requirements are `SPEC-038`
`REQ-3810`–`REQ-3812`.

The set returns a `set_digest` over the ordered list of participants: role, kind,
`stable_id`, version, `plan_hash`, and an “already published” marker. Participant
state is not included in the digest: a plan that moves from `draft` to `ready`
while the operator reads the set does not represent a different decision.

`setup publish confirm --set-digest <digest> --confirm` confirms participants in
set order: components first, then the setup. The command, not the person, owns
the order: a setup confirmed before its pins is rejected by the server-side
`setup_pin_aggregate`, and the rejection is treated as a setup defect.

A participant rejection stops confirmation and moves the set to `partial`.
This state is resumable: published objects remain published, and a repeated
`plan` lists them as `already_published`.

The set is stored locally between the two commands because a `plan_id` cannot be
reconstructed by calculation—it exists only because the plan was created. A
second `plan` for the same setup version replaces the open set.

`publication plan` remains a component command and does not change.

The first-party launch corpus is published through the same authenticated
pipeline, not through a separate catalog command or seed path. The operator
batch `apps/cli/tools/first_party_launch_publication.py` only creates exact
plans, binds bytes, and confirms stored hashes. An already published `X.Y` with
the same digest is skipped by reading the catalog, without seeding or direct
writes. Ordering, resume behavior, and fail-closed behavior belong to
[first-party-launch-publication.md](../operations/runbooks/first-party-launch-publication.md)
and `SPEC-026` `REQ-2628`.
