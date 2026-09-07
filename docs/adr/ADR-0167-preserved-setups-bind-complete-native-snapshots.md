---
description: "ADR-0167: A preserved setup binds a complete provider-owned native snapshot."
last_verified: "2026-09-07"
---

# ADR-0167: Preserved setups bind complete native snapshots

Status: accepted

## Context

Existing user configuration is a setup. Returning to it must restore the whole
configuration, including additions the provider never wrote. A rollback of written
paths alone cannot establish that guarantee. SPEC-068 owns acceptance criteria.

## Decision

The CLI gives preserved native setups local identities bound to verified, retained
provider snapshots. The provider remains the only writer. Complete preservation
captures the declared surface, including empty state, bytes, directories and
supported permissions. Partial mutation backups cannot represent complete setups.

Return preserves current coverage before replacing it and verifies the full
inventory. Unsupported entries, changed preconditions and damaged snapshots refuse.
Shared paths are explicit effects; independent harness operations cannot silently
overwrite conflicting shared configuration.

A documented companion requires an explicit coverage base in plan and status. For
a global `.claude` target, `parent` covers only paths within that target and the
sibling `.claude.json`; other siblings are refused. The isolated process receives
a parent mount to create or remove the companion, while the provider's bound cover
limits actual writes. This does not create a portable component installation route.

Recovery storage stays protected and local. Portable passports cannot carry
credentials or raw recovery bytes. Preservation does not expand installation
ownership. Snapshots retain prior provider state for interruptions before journal
commit. Ordinary return preserves installed setup identity but records a new
return operation.

After a lost response, the CLI recovers the capture identity from the exact stored
plan and fresh status without replaying installation or reinterpreting its terminal
state. A new return selects that identity. Explicit provider recovery archives an
interrupted unpublished capture without deletion before further planning.

## Consequences

Users can select original setups after restarting the CLI and return to edits saved
before later restoration. Retention becomes a setup dependency. The CLI and providers
distinguish complete verified snapshots from narrower legacy mutation backups.

Complete captures use a distinct backup format so legacy provider readers refuse
them rather than interpreting another coverage base as a legacy payload. New readers
retain legacy managed-backup support.
