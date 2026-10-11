---
description: "Keep owner finding decisions separate from immutable technology scan evidence."
last_verified: "2026-10-08"
---

# ADR-0228: Technology finding interpretation

Status: accepted.

## Context

The reference mapping and scan interfaces must correct both recognized and unknown
coordinates, retain comments and classification, and reuse decisions on a rescan.
The original scan document is append-only. The current unmapped queue alone loses
recognized findings and cannot own the full review history.

## Options

- Rewrite stored scans: breaks immutable evidence and retained results.
- Keep decisions only in the current queue: loses scan-specific history on rescan.
- Retain scan evidence and store owner decisions separately: preserves replay and
  lets the same interpretation feed scan detail, mapping and current usage.

## Decision

Use the existing scan, coordinate mappings and canonical project technology
relations. Add one tenant-scoped finding-review record keyed by scan and a
canonical coordinate/context digest. Retain raw detected coordinates in new
handoffs; decode legacy observations through their pinned mapping when possible.
Apply exact scan decisions before same-scope inherited decisions and the latest
published mapping. Owner review has its own revision and the existing atomic
authorization, idempotency receipt and audit boundary. Confirmations publish
immutable mapping snapshots; a rejected finding does not remove the mapping for
other projects. Recompute current usage from the latest scan of each scope.

A repository scan advances the tenant policy revision. To keep a multi-project
launch executable, a completed scan reauthorizes only queued siblings of its own
launch batch, under the organization's lock, at the resulting revision. The
principal, permission, project scope and effect remain identical; the prior
revision is retained. Denied siblings and jobs stale before this scan are not
refreshed. The queue retains its normal stale-envelope and current-permission
checks; an unrelated policy change still rejects the old authority.

## Consequences

Migration 0117 adds review storage and mapping publication timestamps. Existing
scans and relations keep their identifiers. The web shares one review editor
between global mapping and scan detail. Tests cover retained evidence, replay,
revision conflicts, review inheritance and exclusion. Rollback retains the
pre-migration database backup and prior application images; preserve new review
records before downgrading storage.

## Revisit conditions

Revisit the read strategy when scan history volume requires server pagination or
when one technology/context must expose several simultaneous detected versions.
