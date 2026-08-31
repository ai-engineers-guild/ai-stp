---
description: "SPEC-050: Safe catalog enrichment with observable metadata from external catalogs."
last_verified: "2026-08-16"
---

# SPEC-050: External Catalog Enrichment

## Purpose

The platform supplements an exact public component revision with limited observable metadata from `skills.sh`, Nori, and `modelcontextprotocol.com`, without copying artifacts or turning an external signal into a passport, verification, or trust line.

## Scope

This specification covers server-owned metadata adapters, multiple external references, freshness, and safe degradation. Importing bytes, publication, installation, passport modification, and matching by a similar name are out of scope. The general authority model belongs to `SPEC-045` and `ADR-0083`; the wire contract belongs to `docs/contracts/federated-sources.md`.

## Terms

- **Exact coordinate** — a previously stored pair of `provider` and `external_identifier`.
- **Metadata observation** — a restricted allowlist of external fields; neither a passport nor evidence.
- **Policy gate** — stored attribution, terms URL, and an affirmative permission governing fetch and display.

Canonical fields and freshness belong to `docs/contracts/federated-sources.md`.

## Requirements

- `REQ-5001`: Only the `skills_sh`, `nori`, and `modelcontextprotocol` adapters are supported; each returns a common metadata projection and retains its own attribution and terms reference.
- `REQ-5002`: An adapter accepts only the closed allowlist of fields defined by the contract, limits response size, JSON depth and item count, string lengths, and the number of references, and does not execute received content.
- `REQ-5003`: A link is created only from a previously stored exact coordinate. A name, description, URL, or package name without a provider namespace does not create a link.
- `REQ-5004`: One exact revision may have multiple independent references. Deduplication is performed only by provider and external identifier; failure of one reference does not affect the others.
- `REQ-5005`: A successful operation stores `fetched_at`, `checked_at`, and `expires_at`. After the TTL, the last valid value becomes `stale`; a safe fetch/parse failure results in `unavailable` without deleting the last valid observation.
- `REQ-5006`: The cache is bounded by entry count and TTL; fetch uses timeouts, prohibits credentials and redirect escape, bounds the response, and applies a per-provider rate limit.
- `REQ-5007`: Fetching from and displaying a provider are permitted only when attribution, a terms URL, and an affirmative policy gate are stored. A denial disables the adapter fail-closed.
- `REQ-5008`: External metadata always remains an observation and does not change `author_verified`, `component_verified`, `trust_lane`, lifecycle, install eligibility, or ranking without a separate specification.
- `REQ-5009`: Fixtures and a shared conformance suite for each adapter cover the happy path, oversized/poisoned/malformed payloads, unknown fields, timeout/rate limit, `stale`/`unavailable`, and exact-coordinate mismatch.

## States and errors

Freshness is `fresh`, `stale`, or `unavailable`. A closed policy gate, exact-coordinate mismatch, timeout, rate limiting, or parse failure does not create a link or delete the last valid observation. Failure of one reference does not affect the others.

## Security and privacy

An adapter does not execute received content, transmit credentials, or copy artifact bytes. Fetch and display remain fail-closed until attribution, a terms URL, and an affirmative policy gate are stored. The threat model belongs to `docs/engineering/federated-source-threat-model.md`.

## Compatibility and migration

The absence of enrichment and a disabled adapter produce the previous public projection. Rollback hides the additive fields without changing passports, artifacts, or coordinates.

## Acceptance criteria

| Requirement | Executable Evidence |
|---|---|
| `REQ-5001` | Contract and adapter tests confirm the three providers and the common metadata projection. |
| `REQ-5002` | Bounded parser tests reject oversized, poisoned, and malformed payloads and unknown fields. |
| `REQ-5003` | Tests confirm linking only by exact coordinate. |
| `REQ-5004` | Tests confirm multiple independent references and isolated failure. |
| `REQ-5005` | Clock-controlled tests confirm TTL, `stale`, and retention of the last valid value. |
| `REQ-5006` | Tests confirm a bounded cache, timeouts, prohibition of credentials, and a per-provider rate limit. |
| `REQ-5007` | A policy fixture prohibits fetch and projection without attribution/terms permission. |
| `REQ-5008` | Regression tests prove that verification, trust, and install eligibility remain unchanged. |
| `REQ-5009` | The shared conformance suite runs against fixtures for all three adapters. |
