---
description: "Decision to count public usage through short-lived deduplication without user analytics."
last_verified: "2026-08-16"
---

# ADR-0097: Public usage counters without user tracking

Status: accepted.

## Context

The catalog needs comparable detail views and artifact downloads, but a stable
visitor identifier creates a behavioral history, while browser analytics
requires consent. A download also does not prove a successful provider
installation.

## Decision

The platform counts a successful public detail response and successful delivery
of artifact bytes. Repeats are suppressed within a short window by a keyed
digest that cannot be linked across windows; raw network and account/device
identifiers are not stored. Dedup rows have short retention, and only the total
is public.

This is necessary anti-abuse, not optional analytics. The feature flag disables
both recording and projection. Download is not used as install success,
verification, trust, or eligibility.

## Consequences

The aggregate is approximate and is not the number of unique people. Card,
detail, and API read one projection. PostgreSQL provides a unique dedup key and
transactional increment; no browser fingerprint or analytics vendor is needed.

## Reconsideration conditions

Reconsider this decision for consented cohort analytics, a
`provider install receipt`, or a different statutory retention period.
