---
description: "Synchronization event fields, responses, retries, and conflicts."
last_verified: "2026-08-15"
---

# Synchronization event

## Fields

An event contains `event_id`, `entity_id`, `revision_id`, `parent_revision_ids`, `device_id`, `actor_id`, the schema version, the `upsert` or `tombstone` operation, content hash, creation time, idempotency key, and expected cloud head.

Content is transmitted separately or within the event according to the entity schema. The hash is computed under canonical rules. An event contains no secrets, complete project index, or backup bytes.

## Server validation

The server validates the account, device, revocation, entity permission, schema, hash, parents, and expected head. Reusing an idempotency key returns the previous result.

## Entities allowed in MVP

Server flow #179 accepts only `DeveloperPassport`, the allowed summary of the
current `Device`, a private `Component` or `Setup` revision, an
`UnverifiedConsent` record, and their `tombstone`. A full `DevicePassport`,
`ProjectPassport`, `ProjectIndex`, artifact or backup bytes, absolute paths,
secrets, and environment values are not valid event content. Extending this list
changes the wire contract and must go through its owner.

## Response

The response state is `accepted`, `rejected`, `conflict`, or `superseded`. An accepted response returns the cloud head and cursor. A rejection contains a stable code. A conflict contains the common ancestor, local and cloud heads, and affected fields, but performs no silent merge.

## Ordering and retry

An event batch is processed in declared order for one device, but the client assumes no global ordering across devices. A network timeout after acceptance is safely retried with the same key. The handler does not create a second revision or side effect.

## MVP server delivery

For #179, the server stores a durable receipt for every processed event and an
append-only stream containing only accepted events. Revision acceptance, the
server-head transition, receipt creation, and stream append occur in one
transaction. The receipt is returned on retry regardless of whether the client
lost the previous response.

Pull uses an opaque signed cursor bound to the account and a position in this
stream. It is not an offset, stable entity ID, or authorization; the server does
not store a separate cursor row for the client. The batch is bounded. A nonempty
page always returns a cursor for the last sequence emitted, even when no more
rows exist in that read. An empty page does not advance the position: it may
repeat the input cursor or return `null` if none was supplied. This neither means
there will be no future events nor forces a client that has already read events
to restart the stream.

If the expected cloud head is not an ancestor of the new revision, the server
returns `conflict`, does not change the head, and does not append an event. A
valid conflicting revision remains in the ledger only as a parent for a later
explicit merge revision; it does not become the server head and is not visible
through pull. An explicit merge revision with two parents undergoes normal
validation and may be accepted later. A tombstone is also a revision and appears
in the stream; it does not delete history needed to find a common ancestor.

The device comes from the active server session and must match the event. A
revoked device is rejected before any receipt, revision, head, or stream write.
Exact HTTP models, routes, and codes are owned by `packages/contracts` and the
generated OpenAPI when they appear; this document does not create a second list.

## Conflict

The client builds a three-way merge from the common ancestor. Independent fields merge automatically. An incompatible change to one field requires a user decision and creates a revision with two parents.

The local `sync preview --id <stable-id>` command only classifies heads and
computes the content-addressed identifier of a possible merge revision. It does
not move a head, write a revision, contact the server, or change the target. The
generic CLI envelope contains only identifiers and JSON Pointers for conflicting
fields; values remain in the owner-only registry. Automatic field merge is
allowed only for the cross-device developer passport. Device summaries are not
merged across devices, while immutable component/setup objects require a
separate version-conflict path.

Client `sync push` and `sync pull` require explicit confirmation and enabled
`sync.enabled`. Before the first network call, push stores the exact event and
idempotency key, so a lost response causes the same request to be retried. Pull
validates both content-addressed boundaries and applies the entire page with its
opaque cursor in one local transaction. `sync merge` writes only a mechanically
clean developer-passport merge with two parents; conflicting values must still
be resolved by explicitly editing the passport.

For private component/setup objects, the payload additionally carries a bounded
list of released-version metadata without artifact bytes. A collision between
one `X.Y` and another passport digest rolls back the entire page. Durable
continuation after the last nonempty server page uses that position's cursor.
The client does not manufacture a signed cursor itself.

## What the payload may carry

There is one rule and both sides apply it: the client rejects before opening a
socket because a secret that leaves the machine has already left it; the server
rejects again because the client is not the authority deciding what its payload
may contain.

The rule has one owner: `ai_stp_contracts.sync_payload`. The prohibited name
fragments, allowed exceptions, and absolute-path rule live there and are not
repeated here: a rule written twice diverges, and once already did—only the
client received the `required_env` exception, so a complete canonical passport
passed the optional half and was rejected by the authoritative half.

The rule works as follows. A key is prohibited if it contains a prohibited
fragment anywhere, catching `github_token`, `oauth_secret`, and `api_key_value`
without enumeration. This also creates a limitation: a name blacklist over a
typed document rejects fields whose safety is guaranteed by their type. Each
such collision is explicitly allowed and shape-validated rather than accepted
by name—`required_env` carries only `name` and `purpose` and cannot represent a
value; `requires_authorization` is a closed enum. The allowed-collision list is
short and visible; replacing the blacklist with schema-based validation is a
separate decision with an owner.

A rejection names the field path and never outputs the value: the value is
exactly what must not travel.

## Server authority

Author verification, public visibility, grants, and blocking belong to the server and are not merged by the client. Synchronization never changes the harness's installed target directory.
