---
description: "ADR-0186: Tenant-scoped retained employee technology competence links."
last_verified: "2026-09-13"
---

# ADR-0186: Retained employee technology competences

## Status

Accepted.

## Context

Employee competence is not project technology usage or administrative authority.
Corporate Hub requires independent, bidirectionally readable employee technology links.

## Decision

Store one relation per organization, employee account, and technology, with tenant
foreign keys, current/retired state, and revision. Retain retired relations for
reactivation and audit identity. Use existing member.manage authority for writes
and authorize both anchors; competence never creates role bindings or grants.

## Consequences

Roll out an additive table before endpoints and UI. Application rollback retains
the table and history. Technology merge and employee lifecycle handling must
preserve retained relations; no destructive deployment migration is required.
