---
description: "Decision to unify local ports and metadata adapters under a common descriptor without granting them trust or target access."
last_verified: "2026-08-13"
---

# ADR-0083: Federated sources remain external observations

Status: accepted.

## Context

SX/APM provide local setup-store snapshots, while GitHub and ecosystem catalogs
provide remote metadata. Calling them one marketplace erases the distinctions
between local bytes, an external claim, an ASTP passport, and the authority to
modify a harness. Name-based merging additionally permits source takeover.

## Decision

A common versioned `federated-source/1` is accepted, but with distinct kinds:
`local_port` and `metadata_adapter`. The descriptor is always an
`external_observation`, does not raise either verification axis, and prohibits
target writes. A local port may only prepare a separate, confirmed import into
a private draft; a metadata adapter remains read-only.

Identity matches only by provider and exact external identifier. One object may
have several references, but similar names and metadata do not cause an
automatic merge. The ASTP passport remains the sole owner of normative data.

## Consequences

A new source receives its own bounded parser, attribution, TTL/error policy,
and conformance fixture. The `stale` and `unavailable` states do not break the
primary registry. Popularity does not become a trust score. The final target is
still written only by the harness's public provider.

## Reconsideration conditions

The decision is reconsidered if a cryptographically verifiable external
authority, a new source kind, or a secure cross-provider identity protocol
appears.
