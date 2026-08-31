---
description: "SPEC-045: Federated source descriptors and external observation boundaries."
last_verified: "2026-08-16"
---

# SPEC-045: Federated source boundaries

## Purpose

A single shared contract distinguishes a local import port from a network metadata adapter, preserves the attribution and freshness of each external observation, and does not conflate it with a passport, trust, or the right to write the final target.

## Scope

This specification owns the shared source descriptor and conformance rules. The specific local import belongs to SPEC-042, GitHub archive evidence to SPEC-044, and server-owned catalog enrichment to `SPEC-050`. The contract does not copy artifact bytes or create automatic publication or installation.

## Terms

- **Local port** — bounded reading of an explicitly named local snapshot and a separate, confirmed import of a private draft.
- **Metadata adapter** — a read-only observation of an external service without ownership of the canonical passport.
- **Source descriptor** — provider, source kind, exact external identity, attribution, provenance, freshness, and closed permissions.
- **Dedup key** — the exact provider/external identity pair, not a similar name.

## Requirements

- `REQ-4501`: `federated-source/1` has two distinct source kinds — `local_port` and `metadata_adapter` — and preserves the provider, canonical URL, external identifier, time, freshness, provenance, and attribution.
- `REQ-4502`: The descriptor always declares `authority=external_observation`, `author_verified=false`, `component_verified=false`, and `target_write=false`. Popularity, rating, and external claims do not change these values.
- `REQ-4503`: A local port receives `freshness=local_snapshot`, the exact snapshot digest, `checked_at`, and only the capability for confirmed import of a local draft. An adapter receives no import capability, has `fresh`, `stale`, or `unavailable`, and is itself responsible for observing remote rate limits.
- `REQ-4504`: Deduplication is allowed only when both the provider and external identifier match exactly. A matching name, a URL from another provider, or observed metadata does not merge objects; one ASTP object may store several separate references.
- `REQ-4505`: A stale or unavailable reference does not delete a passport, another reference, or a local object. Removal/archive remains an attributed external signal, while source takeover or a change to immutable identity is closed with a conflict.
- `REQ-4506`: Poisoned metadata is constrained by a closed allowlist model, size limits, and the specific adapter's safe parser. An external source does not execute code, write the final target, or become a runtime dependency of the core.
- `REQ-4507`: Adding a provider, source kind, provenance, or authority requires a new compatible descriptor version or an explicit migration and conformance fixture.

## States and errors

Freshness accepts `local_snapshot`, `fresh`, `stale`, or `unavailable`. An identity collision, unknown kind/provider, or contradictory permissions produces a typed failure. The unavailability of one reference does not affect the others.

## Security and privacy

The descriptor does not contain a secret, local path, private bytes, environment value, or device identity. The canonical URL contains no credential or query. The threat model belongs to `docs/engineering/federated-source-threat-model.md`.

## Compatibility and migration

Existing StorePortDescriptor and GitHubArchiveEvidence are converted to the shared descriptor without changing their operational contracts. The platform may store the same descriptor later; this does not give the local CLI account-wide completeness.

## Acceptance criteria

| Requirement | Executable evidence |
|---|---|
| `REQ-4501` | The schema corpus and fixtures convert an SX port and a GitHub observation into distinct kinds under one contract. |
| `REQ-4502` | The model rejects attempts to elevate authority/verification or permit target write. |
| `REQ-4503` | Local snapshot and remote fresh/stale/unavailable preserve distinct capabilities and freshness. |
| `REQ-4504` | An exact key is deduplicated, while the same name from another provider remains a separate reference. |
| `REQ-4505` | A stale/unavailable fixture preserves other references; the SPEC-044 identity collision test is closed with a failure. |
| `REQ-4506` | Conformance references the bounded parser tests from SPEC-042 and SPEC-044, and the descriptor does not accept content/path/secret fields. |
| `REQ-4507` | Closed Literal vocabularies and schema generation require an explicit change for a new provider or kind. |
