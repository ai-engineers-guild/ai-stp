---
description: "Keep corporate installation history separate from heartbeat inventory and runtime usage."
last_verified: "2026-09-25"
---

# ADR-0213: Corporate installation operation facts

Status: accepted. Implemented behavior is recorded in SPEC-093.

## Context

The local installation journal records provider actions and their verified, partial, and rollback outcomes. The corporate usage report currently has assignments and invocation events but no source that proves an installation operation occurred. A heartbeat describes device health, and a later scan can describe current files; neither is an installation event.

## Options

Deriving installation history from scans would invent operation times and actors. Sending a best-effort network event only at apply time would lose offline results. Reusing the durable local operation journal preserves the provider's actual outcome and permits retry without another event store.

## Decision

An operation may be bound to a corporate organization, project, account, and device before the provider changes the target. The binding is immutable. Once the local journal settles, the CLI projects a closed, path-free fact containing the operation ID, action, outcome, time, scope, setup, and exact component coordinates where available. Partial results never claim complete component inventory. The authenticated corporate endpoint binds employee and device to the caller, rejects foreign subjects, and deduplicates by organization and operation ID with a digest check. The CLI marks only accepted and confirmed duplicate facts delivered. Heartbeat and explicit sync may retry undelivered journal facts. This history is independent of invocation counts and inventory scans.

## Consequences

Migration 0097 adds a tenant-isolated server fact table; local registry migration 48 adds the immutable corporate binding and delivery marker. Raw retention and subject erasure include the new table. Old local operations without a binding remain local history and are not attributed retroactively. The report must join only verified results when presenting confirmed installations, while preserving partial and rollback outcomes in detail.

## Revisit conditions

Revisit the transport if journal-backed retries cannot meet measured offline delivery needs or if a provider supplies a stronger native component inventory that can be matched to the exact operation.
