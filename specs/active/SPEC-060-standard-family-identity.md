---
description: "SPEC-060: Coordinated standard-family identity distinct from envelope v1 and protocol v3."
last_verified: "2026-09-05"
---

# SPEC-060: Coordinated standard-family identity

## Purpose

Give agents one machine inventory of every owner-controlled contract axis and
an unambiguous identity for the coordinated standard family, so a textual
rename of protocol v3 or generator `/6` to "v1" cannot be mistaken for the
HTTP/envelope v1 that already exists.

## Scope

Included: inventory of exported schemas and protocol axes, classification of a
document onto one axis, contract digest of that inventory, CLI `contract
inventory` and `version` reporting, and `standard_family` on new local scaffold
writes. Excluded: renaming the `provider-v3` crate or kit directory, changing
HTTP `/v1`, retagging published artifacts, adding a `cli` component kind, and
platform persistence of the family field.

## Terms

- Standard family — the coordinated identity `ai-stp-standard/1`.
- Contract digest — domain-separated hash of the inventory's axes and members.
- Axis — one versioned identity that must not be conflated with another.

## Requirements

- `REQ-6001`: A machine inventory lists every exported schema `$id` and the
  closed protocol axes HTTP `/v1`, envelope `schema_version`, provider protocol,
  kit protocol, component generator, setup generator, and the standard family.
- `REQ-6002`: Classification assigns a document to exactly one axis.
  `standard_family` is the only key that selects the coordinated family.
  `{schema_version: 1}`, `{protocol_version: 1}`, and
  `{standard_family: "ai-stp-standard/1"}` are three different axes.
- `REQ-6003`: Historical component-scaffold descriptors without
  `standard_family` remain validatable and are classified as the generator axis,
  not as the family.
- `REQ-6004`: New component and setup scaffold writes record
  `standard_family` as `ai-stp-standard/1`. Absence is not filled in on read.
- `REQ-6005`: `contract inventory` and `version` report the family and the
  current contract digest. The inventory schema is a CLI model, not an HTTP
  `/v1` route.

## States and errors

Classification may be current, historical (recognized axis, not the current
identity), unknown, or refused when `standard_family` is present but is not the
coordinated identity. Refusals use `AI_STP_SCHEMA_UNSUPPORTED` when a command
must reject a mix; the classifier itself returns problems without writing.

## Security and privacy

The inventory contains no paths, secrets, or account identifiers. The contract
digest is not a capability.

## Compatibility and migration

Old envelopes, kit objects, and scaffold descriptors remain readable. New
writes add `standard_family` without rewriting historical files. A naive
protocol v3→v1 rename is not a migration path.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-6001` | Unit test compares inventory members with `EXPORTED_MODELS` and HTTP/CLI splits. |
| `REQ-6002` | Fixtures from health `/v1`, kit identity, and a `protocol_version: 1` rename classify as three axes. |
| `REQ-6003` | Historical `component-scaffold/3` golden remains validatable and classifies as generator. |
| `REQ-6004` | New `scaffold_plan` descriptor and `.ai-stp-template.json` contain `ai-stp-standard/1`; historical JSON without the field still validates. |
| `REQ-6005` | Process tests: `contract inventory --json` and `version --json` carry the family and a `sha256:` digest; `cli-standard-inventory` is not an HTTP model. |
