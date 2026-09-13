---
description: "ADR-0185: Employee display names are organization-scoped profile data."
last_verified: "2026-09-13"
---

# ADR-0185: Tenant member display names

## Status

Accepted.

## Context

Corporate employee edits must not change the same account's public profile or
its identity in another organization. Role management is a separate operation.

## Decision

Store an optional display name on organization membership. Backfill existing
names from accounts and prefer the tenant name in every corporate member view.
Retain the account fallback for legacy null names. A dedicated profile mutation
uses current `member.update` authority, member revision, and durable idempotency.
It changes the tenant name and member revision without changing authorization
policy, roles, bindings, or the account profile.

## Consequences

Existing DTO shape remains compatible. Deploy the additive column before API.
Application rollback retains the column and tenant names; dropping the column
requires a verified recovery copy. Profile changes remain audited.
