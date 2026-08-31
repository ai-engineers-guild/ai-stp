---
description: "SPEC-009: Local registry and synchronization."
last_verified: "2026-08-04"
---

# SPEC-009: Local registry and synchronization

## Purpose

The local registry remains a fully functional offline source for the device, while optional cloud synchronization preserves history, does not lose concurrent changes, and does not modify the installed harness.

## Scope

This includes SQLite, local content-addressed storage, revisions, device heads, outbound and inbound journals, cursors, fast-forwarding, three-way merging, conflicts, and deletion markers. Synchronization of backup bytes and a silent last-write-wins rule are out of scope.

## Terms

- `EntityRevision` — a content-addressed value with parent revisions.
- `DeviceHead` — the local head of an entity.
- `SyncEvent` — an idempotent change between a device and the server.
- `ConflictRecord` — an explicit concurrent change requiring a merge or decision.

## Requirements

- `REQ-901`: SQLite uses migrations, write-ahead logging, foreign keys, transactions, and restrictive filesystem permissions.
- `REQ-902`: Ordinary reads and state checks do not create data or change content timestamps.
- `REQ-903`: Revisions are addressed by a canonical content hash and contain parents, schema version, author, device, and operation.
- `REQ-904`: If one head is an ancestor of the other, synchronization uses a fast-forward.
- `REQ-905`: Divergent history uses a field-level three-way merge from a common ancestor.
- `REQ-906`: Concurrent incompatible changes to the same field create an explicit conflict without silent overwriting.
- `REQ-907`: Deletion is represented by a deletion marker and propagated as a revision.
- `REQ-908`: Outbound and inbound journals, as well as server handlers, are idempotent by event key and safe to retry.
- `REQ-909`: Synchronization never applies a setup or changes the harness target directory without a separate installation plan.
- `REQ-910`: Partial synchronization retains the journal and cursor and is not reported as successful.
- `REQ-911`: The full device passport never leaves the device; only its permitted summary from `docs/contracts/device-passport.md` is synchronized as a separate entity for that device, no three-way merge is performed between summaries from different devices, and only the developer passport is merged across devices.
- `REQ-912`: Concurrent offline creation of versions of the same object on two devices is reconciled during synchronization without rewriting immutable data: if one `X.Y` number is occupied by different hashes, the first revision accepted by the server retains the number, the losing unpublished version is automatically reissued under the next available minor number with the same content and a new passport, a `ConflictRecord` is created, and a published number is never moved this way.

## States and errors

A synchronization session has the states `offline`, `up_to_date`, `pushing`, `pulling`, `conflict`, `partial`, and `failed`. A server response has the states `accepted`, `rejected`, `conflict`, and `superseded`. A revoked device receives a permanent authorization error; a network timeout permits a retry with the same idempotency key.

## Security and privacy

For every event, the server verifies the device, account, permission, schema, and expected head. The project index belongs to the local device. Published versions, author verification, visibility, and permissions belong to the server and are not merged by the client.

## Compatibility and migration

Old and new clients exchange only a supported major schema version. Migration preserves revision identifiers or creates an explicit derived revision. Compaction does not delete a common ancestor needed by supported devices until the retention rule has been satisfied.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-901` | A SQLite integration test checks the journal, foreign keys, migrations, transaction rollback, and file mode. |
| `REQ-902` | A read test compares database and filesystem state before and after. |
| `REQ-903` | Property tests confirm the canonical hash and parent graph. |
| `REQ-904` | A two-device fixture pushes and pulls using a fast-forward. |
| `REQ-905` | Independent field changes are merged with two parents. |
| `REQ-906` | Divergence in one field creates a `ConflictRecord`. |
| `REQ-907` | Replaying a deletion marker hides the object without losing audit history. |
| `REQ-908` | Replaying one event does not create a second revision or effect. |
| `REQ-909` | An end-to-end synchronization test compares the target hash before and after. |
| `REQ-910` | Fault injection after every persistence point confirms a resumable partial state. |
| `REQ-911` | A two-device fixture synchronizes two separate summaries without attempting to merge them, and synchronization events contain neither the full device passport nor absolute paths. |
| `REQ-912` | A fixture with two offline devices using the same number and different hashes retains the number of the first accepted revision, reissues the second under the next number with a `ConflictRecord`, and does not change any published snapshot. |
