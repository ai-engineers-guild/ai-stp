---
description: "SPEC-033: Public beta-support labels, evidence, and freshness."
last_verified: "2026-08-09"
---

# SPEC-033: Public beta-support labels, evidence, and freshness

## Purpose

Issue #193 must make the actual harness support level observable in the API and
web after the related P11-01, P11-02, and P11-03 tasks for Pi, OpenCode, and
Grok Build are completed. The user must see not only the harness name but also
the basis for the `beta` label, the evidence state, and its freshness.

This specification supplements `SPEC-001`, `SPEC-008`, `SPEC-021`, and `SPEC-022`.
The domain and wire model of the public read-model belongs to
`ADR-0072-public-beta-support-evidence-read-model.md` and the contracts in
`docs/contracts/`.

## Scope

Included:

- a public support-tier model of `primary` or `beta`;
- a safe public projection of harness support evidence;
- evidence freshness and eligibility states;
- API and web filters by support tier and state;
- beta labels, evidence, and freshness on catalog cards and pages;
- bilingual messages and identical API and web semantics;
- fixtures and negative checks for `stale`, `missing`, and `not_verified`
  evidence.

Excluded:

- implementation of the Pi, OpenCode, or Grok Build provider;
- changes to the CLI, local registry, or canonical Agent Skill;
- changes to `trust_lane`, `author_verified`, or `component_verified`;
- automatic promotion from beta to primary;
- blocking the first MVP release because beta evidence is incomplete;
- publication of secrets, internal logs, credentials, or private artifacts.

## Terms

- **Support tier** — the declared product support level for a harness: `primary`
  or `beta`.
- **Support evidence** — a verifiable record of an exact provider release and
  the result of its end-to-end verification for a specific environment matrix.
- **Freshness** — the result of comparing the current time with the permitted
  evidence lifetime.
- **Support state** — the public state of a support line: `verified`,
  `stale`, `missing`, or `not_verified`.

Support tier and support state are independent fields. `beta` does not mean
`experimental`, and `experimental` does not mean a beta provider.

## Requirements

- `REQ-3301`: The API and web represent support tier only as `primary` or
  `beta`; the value matches the canonical harness set in `SPEC-001` and is not
  derived from `trust_lane`.
- `REQ-3315`: The tier composition is defined exactly as follows: `claude-code`, `codex`, and
  `grok-build` are `primary`; `pi`, `opencode`, `cursor`, and `antigravity` are `beta`.
  The value has a single owner and is not repeated in a second table. The tier is
  a product decision: under `REQ-3306`, evidence does not promote it, while under
  `REQ-3307`, the absence of a recorded run is reflected in support state and does
  not lower the tier.
- `REQ-3302`: A public card and exact object version show support tier, support
  state, and a safe evidence summary for `latest_harness_id`.
- `REQ-3303`: `support evidence` is bound to an exact `provider release`, `exact
  commit` or `digest`, `harness`, `operating system`, and `architecture`;
  evidence without exact provenance cannot yield the `verified` state.
- `REQ-3304`: `verified` is returned only when all mandatory evidence required by
  the current support policy is present, has the `passed` result, and has not expired.
- `REQ-3305`: Expired mandatory evidence receives the `stale` state, while missing
  mandatory evidence receives `missing`; neither state is displayed as verified support.
- `REQ-3306`: Evidence with a `failed`, `degraded`, `not_run`, or other result not
  accepted by policy receives `not_verified` and does not promote support tier.
- `REQ-3307`: Missing or stale beta evidence is represented honestly and does not
  block the first MVP release; a line without a recorded run is not called
  supported and receives `not_verified`.
- `REQ-3308`: Support evidence does not change `author_verified`,
  `component_verified`, or `trust_lane`; these axes continue to be computed under
  `ADR-0016`, `ADR-0026`, and `ADR-0032`.
- `REQ-3309`: API filters accept only declared support tier and support state values,
  preserve other filters, and do not change request-scoped consent for the
  `experimental` line.
- `REQ-3310`: Web does not compute support state, freshness, or evidence eligibility
  itself; it displays values from the canonical API read-model.
- `REQ-3311`: Russian and English locales show identical fields, states, reasons,
  and consequences; user-facing strings are not hardcoded in components.
- `REQ-3312`: The public projection contains no credentials, secrets, internal logs,
  private object keys, non-public URLs, or data that could provide access to an
  evidence artifact.
- `REQ-3313`: Every public evidence record contains safe verification identifiers,
  source, exact release reference, `observed_at`, and, where applicable, `expires_at`;
  the timestamp is not replaced with the web render time.
- `REQ-3314`: Existing clients unaware of additive fields continue to decode the
  supported major API version; new clients reject unknown enum values and safely
  display `not_verified` only according to contract rules, not because a field is absent.

## States and errors

Canonical support evidence states:

```text
verified      mandatory evidence is present, passed, and still valid
stale         mandatory evidence existed, but its validity period expired
missing       mandatory evidence was not published
not_verified  evidence exists but does not satisfy the current policy
```

An invalid or incompatible filter returns a typed API error. A corrupted or
contradictory server record does not become `verified`: the server returns a safe
error or projects `not_verified` under `ADR-0072`. Web shows the dependency state
and `X-Request-Id` without disclosing the internal cause.

## Security and privacy

Support evidence is public metadata, not public access to an artifact. A public
client does not receive a storage key, signature, token, private link, or report
content. The provider release is verified under the existing trust policy, and
provenance verification does not mean the platform is safe in every scenario.

The `verified` status grants no right to install and does not move an object into
`authoritative`. Installation eligibility and trust line remain separate decisions.

## Compatibility and migration

Wire-field changes are made additively through the canonical `packages/contracts`
models, generated schemas, and OpenAPI. The web client is regenerated from the
updated contract. Existing catalog rows receive the safe `missing` state until
the corresponding evidence is imported; historical publications and their
passports are not rewritten.

Rollback disables the new filters and support-evidence projection while preserving
old catalog fields and historical evidence. Deleting evidence or recalculating status
does not delete published versions or change already installed targets.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-3301` | Contract test accepts only `primary`/`beta` and proves independence from `trust_lane`. |
| `REQ-3315` | Test proves the exact tier composition and that no second tier table exists in the tree. |
| `REQ-3302` | API and web golden tests find tier, state, and evidence summary on card and exact-version routes. |
| `REQ-3303` | Negative test rejects evidence without exact release, digest, or matrix context. |
| `REQ-3304` | Fixture with a complete fresh set of passed evidence receives `verified`. |
| `REQ-3305` | Fixtures with expired and missing mandatory evidence receive `stale` and `missing`. |
| `REQ-3306` | Fixture with failed/degraded/not_run evidence receives `not_verified`. |
| `REQ-3307` | Release gate verifies that an incomplete beta line neither blocks MVP nor is called supported. |
| `REQ-3308` | Contract test changes support evidence and confirms that trust axes remain unchanged. |
| `REQ-3309` | API tests verify enum validation and independence from experimental consent. |
| `REQ-3310` | Static/component test prohibits web-side status computation. |
| `REQ-3311` | Locale parity test compares ru/en fields, states, and actions. |
| `REQ-3312` | Secret/privacy scan and response inspection find no prohibited values in the public projection. |
| `REQ-3313` | Schema test requires provenance and timestamps and prohibits render-time freshness. |
| `REQ-3314` | Compatibility test accepts the old additive response and verifies safe handling of new enum values. |
