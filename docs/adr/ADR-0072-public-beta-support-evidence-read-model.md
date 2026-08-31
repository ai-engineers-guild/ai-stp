---
description: "Decision on the public read-model for beta support, evidence, and freshness."
last_verified: "2026-08-09"
---

# ADR-0072: Public read-model for beta support, evidence, and freshness

Status: proposed.

## Context

Issue #193 requires displaying in the API and web the beta status, current evidence, and its freshness after completion of P11-01, P11-02, and P11-03 for Pi, OpenCode, and Grok Build.

The project already has independent concepts:

- `primary`/`beta` as the harness support tier;
- `trust_lane` as the trust line of the published object;
- `author_verified` and `component_verified`;
- publication evidence with a result and `expires_at`.

Mixing these concepts would lead to the false conclusion that a beta provider is an experimental object, or that a verified passport proves end-to-end harness support. A separate public read-model is needed that does not create a second policy engine in web.

## Alternatives

### 1. Compute beta status in web

Simple to implement, but violates `ADR-0018` and `SPEC-022`: web would become a second source of business logic, and the API, CLI, and different locales could display different results.

### 2. Derive status from `trust_lane` or `component_verified`

Requires no new data, but is semantically incorrect. These fields represent trust in a specific object version and completeness of publication checks, not provider support.

### 3. Store support evidence separately and expose a safe server projection

Requires a new read-model and an additive wire contract, but preserves independent axes, exact provenance, consistent freshness calculation, and a safe public boundary.

### 4. Publish raw provider reports

Provides more detail, but exposes internal logs, topology, credentials, or unverified links and makes the format of external repositories part of the API.

## Decision

Alternative 3 is accepted.

### Separate support evidence projection

The platform stores or imports a normalized support evidence record separately from the object passport and publication evidence. It is associated with:

- `harness_id`;
- provider release identity;
- exact commit or digest;
- operating system and architecture;
- policy version;
- check id and result;
- `observed_at` and `expires_at`.

Only a safe projection is exposed through the public API. Raw reports, signatures, storage keys, credentials, and internal logs are not exposed.

### Canonical state calculation

The server computes the support state according to the current policy:

```text
verified      all required checks passed and evidence has not expired
stale         required evidence has expired
missing       required evidence is absent
not_verified  evidence does not satisfy policy
```

Freshness is calculated using server time and stored timestamps, not during web rendering. Web receives the computed state and only displays it.

### Independent axes

Support tier/state do not change:

- `trust_lane`;
- `author_verified`;
- `component_verified`;
- installation eligibility.

`beta` denotes the product support tier. `experimental` denotes the object's trust line. An object may be beta and authoritative, or beta and experimental, if the other rules permit it.

### Public catalog API

Support projection fields are added additively to catalog summary/detail/version responses. Support tier/state filters are API request parameters and do not change request-scoped consent for `experimental`.

An old client that does not know about the new fields continues to work within the current major version. The value for absent evidence is `missing`, not `verified`.

### Source of provider evidence

P11-01, P11-02, and P11-03 supply evidence from public provider repositories. The platform accepts only evidence associated with an exact release and verified against the current release policy. The existence of an issue, README, or arbitrary text does not constitute evidence.

## Consequences

- `packages/contracts` receives new models for the support projection and filters;
- `schemas/v1/openapi.json` and the generated web client are updated from the models;
- API/platform receive a single calculation for support state and freshness;
- web displays only the server projection;
- a migration or separate storage/read-model for support evidence is introduced;
- fixtures cover `fresh`, `stale`, `missing`, `failed`, and conflicting evidence;
- release evidence is associated with the exact provider SHA;
- existing catalog rows are not rewritten and receive `missing` until support evidence is imported;
- beta evidence does not block the first MVP release;
- rollback can disable the projection and filters without deleting historical data.

## Security

The public projection is not a bearer credential and does not contain addresses through which a private artifact can be obtained. Unknown, corrupted, or conflicting evidence does not raise the status. A parsing or provenance error must not be masked as a fresh verification.

## Reconsideration Conditions

The ADR is reconsidered if:

- provider evidence becomes credentialed/private and requires a separate access model;
- raw reports or interactive artifacts need to be displayed;
- support policy ceases to be shared across provider releases;
- the API requires a breaking change instead of an additive projection;
- the volume of evidence requires a separate analytical read-store rather than a transactional projection.
