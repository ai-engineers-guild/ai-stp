---
description: "SPEC-064: Per-adaptation evaluation evidence for a component version."
last_verified: "2026-09-06"
---

# SPEC-064: Per-adaptation evaluation evidence

## Purpose

A component version with several harness adaptations must not become verified
because only the first projection passed.

## Scope

Included: local evaluation coordinates and check results keyed by adaptation.
Excluded: platform persistence and web rendering of assessments (`#146`).

## Terms

- Adaptation — one harness-native implementation of a component version.
- Coordinate — the exact version and adaptation identity in an eval plan.

## Requirements

- `REQ-6401`: Evaluation enumerates every adaptation of the pinned version.
- `REQ-6402`: Each adaptation is scanned at its projection digest. Mixed
  pass/fail is visible per adaptation without collapsing into one surface set.
- `REQ-6403`: Author attestation may bind adaptation id, projection digest,
  scope, provider profile, OS, and architecture. Unset optional fields keep
  historical signed payloads unchanged.
- `REQ-6404`: Changing evidence does not mint a component version.

## States and errors

Eval check status remains `passed`, `failed`, `not_run`, or `degraded`. A
missing adaptation id on a stored coordinate loads every adaptation of that
version. Replay of attestation with a different adaptation id produces a
different digest.

## Security and privacy

Evidence does not include secrets, local paths, or raw scanner output. Optional
attestation fields are omitted from the signed payload when unset so historical
records keep their digest.

## Compatibility and migration

Existing single-adaptation evaluation remains valid. New optional attestation
fields default to absent. Changing evidence never rewrites a component version.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-6401` | A two-adaptation setup plan lists both harnesses. |
| `REQ-6402` | Static-contract results include mixed `passed`/`failed` with adaptation ids. |
| `REQ-6403` | Attestation digest changes when `adaptation_id` changes; omitted fields are absent from the signed payload. |
| `REQ-6404` | Eval result states `immutable_published_bytes_changed` is false. |
