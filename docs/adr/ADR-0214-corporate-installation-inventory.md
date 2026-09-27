---
description: "Keep opt-in installation inventory independent of operation history and usage counts."
last_verified: "2026-09-25"
---

# ADR-0214: Corporate installation inventory

Status: accepted. Implemented behavior is recorded in SPEC-094.

## Context

The installation journal proves provider operations but cannot detect later manual changes. Heartbeat health proves the device reported, not which component files remain. Existing native discovery already gives bounded, content-free observations and a completeness signal.

## Options

Adding component lists to the heartbeat would couple a health check to a potentially slow scan. Inferring removal from a failed scan would produce false absence. A separate opt-in snapshot stream preserves both boundaries.

## Decision

The organization controls an `inventory_scan_enabled` policy independent of heartbeat enablement. When enabled, a successful heartbeat triggers discovery of global harness configuration and locally linked corporate project roots. The scan compares the newest settled corporate provider result per target with its exact cached bundle. Bundle bindings supply stable IDs and versions; the managed path diff distinguishes present, modified, and missing files. Discovery entries outside verified managed paths are external. If a managed baseline cannot be checked, their origin is unknown and the scope is incomplete. The CLI queues path-free, per-scope snapshots before delivery. Each snapshot has its own completeness flag. Missing roots, discovery failures, and bounded results remain incomplete. The server binds snapshots to the authenticated employee and device, checks organization and project, and stores idempotently. A report may use only a complete successful scope scan to infer absence; incomplete checks leave installation state unknown. Inventory never emits invocation events.

## Consequences

Local registry migration 49 adds a scoped outbox. Server migrations 0098 and 0099 add the independent policy flag and tenant-isolated snapshots. Discovery coordinates are hashed before transmission; no absolute path or component content is included. Managed coordinates come from the exact cached bundle. Existing heartbeat cadence stays unchanged when scanning is disabled.

## Revisit conditions

Revisit the snapshot size cap if measured project inventories exceed the bounded request, or if a provider exposes a stronger version-aware native inventory.
