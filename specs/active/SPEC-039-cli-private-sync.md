---
description: "SPEC-039: CLI synchronization of the private registry between devices."
last_verified: "2026-08-13"
---

# SPEC-039: CLI synchronization of the private registry

## Purpose

The CLI transfers permitted private revisions between devices through the server
ledger without uploading source code, the full device passport, project index,
secrets, or local paths. The local revision graph remains responsible for
merging; the server accepts events and provides an ordered stream.

## Scope

The scope includes `sync push`, `sync pull`, `sync preview`, and `sync merge`,
durable event/idempotency keys, receipts, remote-head mappings and account
cursors, upserts, tombstones, fast-forwards, two heads, clean three-way merges,
explicit field conflicts, and released-version collisions. Wire models belong
to `packages/contracts`; the server-side state machine is defined by `SPEC-025`.

The scope excludes modifying the server ledger, synchronizing artifact bytes,
the project passport/index, the full device passport, installation into a target,
and automatic value selection during conflict resolution.

## Terms

- **Local revision** — a content-addressed passport in the device's SQLite graph.
- **Remote revision** — a server ledger event whose identifier additionally
  binds the account, device, operation, and local payload.
- **Indeterminate result** — the server may have accepted the push, but the
  client did not receive a contract-compliant receipt and therefore must retry
  the same event.

## Requirements

- `REQ-3901`: Push constructs an event only from a local allowlisted revision,
  computes the server revision/content digest over the canonical domains, and
  durably stores the exact event, idempotency key, and expected remote head
  before issuing the HTTP request.
- `REQ-3902`: An indeterminate network result does not create a new event. The
  next invocation retries the stored request; accepted ancestors are not sent
  again, and an unaccepted child does not overtake its ancestor.
- `REQ-3903`: Before writing, pull validates the account and canonical revision
  id; the client validates the content digest, entity kind/id, and the
  passport's internal revision id. The entire page and opaque cursor are
  committed in a single SQLite transaction; an error rolls back everything.
- `REQ-3904`: A received fast-forward advances the local head according to the
  graph's normal rule. Divergence preserves both heads; changes to independent
  fields produce a mechanical merge candidate, while a JSON Pointer changed on
  both sides remains an explicit conflict.
- `REQ-3905`: `sync merge` requires confirmation and records only a clean
  developer-passport merge with two exact parents. Components and setups are
  not merged field by field.
- `REQ-3906`: A tombstone is a separate replay-safe event, requires an accepted
  remote head, does not delete history, and, upon pull, idempotently closes the
  revision to normal local reads.
- `REQ-3907`: Metadata for released component/setup versions is synchronized
  together with the private revision. The same `stable_id + X.Y` with a
  different digest rejects the entire page as `AI_STP_CONFLICT`; the version
  number is not reassigned.
- `REQ-3909`: An event named to `sync pull --skip-event` is abandoned on this device for the account and honoured by every later pull without being named again; the answer lists what a page skipped, and a refusal that stops the walk names the exact command that moves past the event.
- `REQ-3908`: Sync is disabled by default; network commands require explicit
  confirmation and an active session, and transmit the bearer token only to a
  verified endpoint. Preview and local merge do not modify the harness target.

## States and errors

Receipt states `accepted`, `rejected`, `conflict`, and `superseded` are stored
without reinterpretation. A transport failure remains retryable and preserves
the pending event. A mismatch in content, account, or coordinates is a
validation failure before any local write. A version collision and two
incompatible heads are conflicts with no winner selected.

## Security and privacy

The allowlist is closed at the event level. The payload does not contain source
bytes, credentials, environment values, absolute paths, backups, the project
index, or the full device passport. The common command envelope exposes
identifiers, receipt state, and the JSON Pointers of conflicting fields, but
not the values of those fields.

## Compatibility and migration

SQLite migration 17 additively introduces the event journal, remote heads, and
cursor, and provides a rollback path that removes the new tables. On the first
push, old revisions are sent from the root to the head. The client neither
decodes nor creates the server cursor.

## Acceptance criteria

| Requirement | Evidence |
| --- | --- |
| `REQ-3901` | A unit/transport test compares the request against server canonicalization and verifies the durable row before the call. |
| `REQ-3902` | A mock drops the first response; the retry observes the same event/idempotency key and proceeds with the child only after receiving the ancestor's receipt. |
| `REQ-3903` | A tampered page leaves no revision/event/cursor; a valid page applies them atomically, and replay is a no-op. |
| `REQ-3904` | Two SQLite databases exercise root, fast-forward, divergence, pulling the second head, and deterministic merge preview. |
| `REQ-3905` | A test records a merge with two parents and rejects an overlapping field conflict. |
| `REQ-3906` | A tombstone retries the same event, has a remote parent, and a repeated pull does not alter the initial deletion mark. |
| `REQ-3907` | Two databases record different digests under the same X.Y; pull rolls back the page and cursor. |
| `REQ-3908` | Registry/process tests verify confirmations, the disabled guard, the bearer boundary, and the absence of prohibited data. |
| `REQ-3909` | A transport test names an event once, re-reads the same page with nothing named, and finds it skipped; the refusal's first next action carries the exact event id. |
