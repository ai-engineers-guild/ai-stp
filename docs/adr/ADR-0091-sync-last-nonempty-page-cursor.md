---
description: "Decision to return a signed cursor on every non-empty sync pull page."
last_verified: "2026-08-15"
---

# ADR-0091: Cursor on the last non-empty sync pull page

Status: accepted.

## Context

`ADR-0045` and `SPEC-025` already require an opaque account-bound cursor for the
ordered server outbox. The server does not store a separate client cursor
string: the client must retain the issued token and return it verbatim.

The pull implementation and the previous contract text treated `next_cursor`
like a catalog page: the field is `null` when `has_more` is false. The last
non-empty page therefore left no position. The client cannot manufacture the
token itself: it is signed and bound to the account. The next poll without a
cursor reads the stream from the beginning. Over time, this causes unbounded
history replay and directly contradicts `SPEC-025` `REQ-2504`.

The catalog rule in `docs/contracts/http-api.md` is different: an object list is
not a durable resume stream, and `next_cursor: null` remains on the last catalog
page. The two surfaces must not be conflated.

## Options

1. Leave `null` on the last page. The client reads the stream from the beginning
   each time. This preserves the catalog shape but makes durable sync impossible
   and expands reads as the outbox grows.
2. Store each client's cursor on the server. This provides resume without
   changing the response, but introduces server-side session state and
   contradicts `REQ-2504`.
3. A non-empty page always returns a cursor for the last emitted sequence. An
   empty page does not advance the position or force a client that has already
   read the stream to start over.

## Decision

Option 3 is accepted.

The cursor remains opaque, signed, and account-bound. It carries only the
position in the current account's outbox. An empty stream without an input
cursor may still return `next_cursor: null`: the client has not consumed any
events yet.

Catalog pages and other object-list pages do not change.

## Consequences

- the `PageInfo` wire model already allows both a string and `null`; the
  population rule for sync pull changes, not the schema;
- fixtures and OpenAPI examples for `pullSyncEvents` must show a non-null cursor
  on a one-event final page;
- the CLI only stores and returns the token; client-side cursor construction is
  prohibited;
- forged and foreign cursors continue to be rejected;
- reverting to last-page `null` for sync pull breaks durable polling again.

## Reconsideration conditions

The decision is reconsidered if sync stops being a synchronous read from the
PostgreSQL outbox and becomes a separate broker, or if the cursor becomes a
durable server-side session. A new ADR is then required. This decision does not
reopen the catalog rule.
