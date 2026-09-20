---
description: "Decision to record significant and hard-to-reverse architectural changes in ADRs."
last_verified: "2026-09-20"
---

# ADR-0001: Record architecture decisions

Status: accepted. Accepted on 2026-07-28. Extended by ADR-0194.

## Context

The product connects local state, the cloud, multiple harnesses, and five external provider repositories. Implicit decisions quickly diverge between code and documentation.

## Decision

A separate ADR is required when a change:

- changes the source of truth;
- changes a public contract;
- creates or removes a mandatory dependency;
- changes security, authorization, or privacy;
- changes the versioning, synchronization, or provider lifecycle model;
- requires coordinated changes across multiple repositories.

## Consequences

An ADR explains the decision and constraints, but does not replace an active specification, tests, or current documentation.
