---
description: "Template for a verifiable specification."
last_verified: "2026-08-03"
---

# SPEC-NNN: Short title

## Goal

The observable result that must become possible.

## Boundaries

What is included and what is explicitly excluded.

## Terms

Only new or clarified terms.

## Requirements

Requirement identifiers belong to their specification block: `SPEC-NNN` owns
the `REQ-NNNxx` range, where `xx` is the ordinal within the specification. For
example, `SPEC-006` owns `REQ-601`…`REQ-6nn`. A requirement number is never
reused, even after the requirement is removed.

- `REQ-NNN`: One observable and verifiable requirement.

## States and errors

Successful, erroneous, partial, and unknown states; stable error codes and recovery.

## Security and privacy

Trust boundary, data, authority, logging, and prohibited leaks.

## Compatibility and migration

Old and new clients, schema version, rollout order, and rollback.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-NNN` | Exact test, contract check, or other observable result. |
