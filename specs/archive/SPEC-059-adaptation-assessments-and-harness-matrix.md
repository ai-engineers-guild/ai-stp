---
description: "Superseded historical SPEC-059: Platform-owned adaptation assessments and the public per-harness support matrix."
last_verified: "2026-09-06"
---

# SPEC-059: Adaptation assessments and the harness support matrix

Superseded by
`SPEC-064-component-projections-assurance-and-portability.md`. This historical
record is restored to preserve the contract that accompanied the original
adaptation-matrix implementation; `SPEC-059` was later reused by an unrelated
active specification and must not be reused again.

## Purpose

Define platform-owned mutable assessment of an immutable component adaptation
and its safe public catalog projection without changing the passport.

## Scope

The specification covered durable adaptation-assessment rows, exact target
identity, verification and recommendation states, effective freshness, detail
projections, and web display. It excluded CLI eligibility, setup aggregation,
search-card expansion, and provider acquisition.

## Requirements

- `REQ-5901`: Persist one idempotent assessment for exact component version,
  adaptation, harness, provider, OS, architecture, and policy identity.
- `REQ-5902`: Store `not_verified`, `verified`, `stale`, or `failed`; expiry
  makes an otherwise verified assessment effectively stale.
- `REQ-5903`: Store `not_recommended` or `platform_recommended`; authors cannot
  issue platform recommendation.
- `REQ-5904`: Effective recommendation requires effective verified state.
- `REQ-5905`: Assessment does not mutate the passport and combines multiple
  scopes conservatively.
- `REQ-5906`: Component detail and exact version expose a support matrix while
  search summary does not expose the full matrix.
- `REQ-5907`: API and web consume the generated contract and localized labels.
- `REQ-5908`: CLI gains no assessment cache or provider behavior from this
  platform specification.
- `REQ-5909`: Missing assessment projects explicit not-verified and
  not-recommended defaults without invented target context.

## States and errors

Fresh verified evidence could expose stored recommendation; expired verified
evidence became stale; every non-verified state exposed no recommendation.

## Security and privacy

Public context included stable provider/policy/platform identities and
timestamps, but no credentials, storage keys, raw reports, or private bytes.

## Compatibility and migration

The original change was additive. The successor expands assessment identity,
search/card summaries, scope treatment, evidence reuse, and migration behavior.

## Acceptance criteria

Historical tests covered composite identity, all states, expiry, platform-only
recommendation, immutable technical support, detail matrices, generated-client
parity, CLI non-effects, and missing-assessment defaults.
