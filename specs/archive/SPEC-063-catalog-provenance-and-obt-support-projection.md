---
description: "Superseded SPEC-063: Direct catalog provenance links and OBT support projection."
last_verified: "2026-09-06"
---

# SPEC-063: Catalog provenance and OBT support projection

Superseded by `SPEC-065-setup-families-and-harness-invariant-alignment.md`.
The successor retains passport provenance and canonical OBT support projection
while replacing direct related-ID presentation with explicit setup families and
version alignment.

## Purpose

Make setup provenance created by recast durable and visible in catalog and
owner setup reads, and make the catalog/web support projection represent the
current OBT beta line of all seven supported harnesses.

## Scope

This specification covered persistence and presentation of `ported_from` and
`related_setup_ids`, canonical support-tier projection, migration correction,
and the seven-harness web surface. It did not define synchronization, merging,
or shared setup versions.

## Requirements

- `REQ-6301`: Seed and publication paths preserve submitted setup provenance.
- `REQ-6302`: Public setup detail exposes latest setup provenance.
- `REQ-6303`: Owner exact-version reads expose the same provenance.
- `REQ-6304`: Public web renders source and related setup links as read-only
  navigation.
- `REQ-6305`: Search derives support tier from canonical `SUPPORT_TIERS`; all
  canonical OBT harnesses project as `beta` independently of evidence.
- `REQ-6306`: A forward migration corrects historical search projection rows.
- `REQ-6307`: Web harness surfaces cover every canonical harness.
- `REQ-6308`: Public projection contains no secret, credential, personal data,
  or fabricated authorization.

## States and errors

Absent provenance was represented by `ported_from: null` and
`related_setup_ids: []`. Provenance implied no compatibility or mutation.

## Security and privacy

Existing visibility and owner authorization applied. Relationships carried
public setup identifiers only.

## Compatibility and migration

The public fields were additive and search tiers were a derived projection.
Historical passports remained immutable.

## Acceptance criteria

Historical acceptance belonged to the implementation of issues #139 and #140.
The successor owns all future executable oracles.
