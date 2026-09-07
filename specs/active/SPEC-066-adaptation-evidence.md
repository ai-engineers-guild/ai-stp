---
description: "SPEC-066: Per-adaptation evaluation evidence for a component version."
last_verified: "2026-09-06"
---

# SPEC-066: Per-adaptation evaluation evidence

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

- `REQ-6601`: `eval component` enumerates every adaptation of the pinned
  version. A setup evaluation enumerates only the adaptation for that setup's
  harness.
- `REQ-6602`: Each adaptation is scanned at its projection digest. Mixed
  pass/fail is visible per adaptation without collapsing into one surface set.
- `REQ-6603`: Author attestation may bind adaptation id, projection digest,
  scope, provider profile, OS, and architecture. Unset optional fields keep
  historical signed payloads unchanged.
- `REQ-6604`: Changing evidence does not mint a component version.

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
| `REQ-6601` | A Claude setup with a Codex sibling lists only Claude. `eval component` lists both. |
| `REQ-6602` | Static-contract results include mixed `passed`/`failed` with adaptation ids. |
| `REQ-6603` | Attestation digest changes when `adaptation_id` changes; omitted fields are absent from the signed payload. |
| `REQ-6604` | Eval result states `immutable_published_bytes_changed` is false. |
