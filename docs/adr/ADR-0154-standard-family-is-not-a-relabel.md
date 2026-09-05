---
description: "Decision that the coordinated standard is a new identity, not a rename of HTTP v1, envelope schema_version, kit protocol v3, or generator generations."
last_verified: "2026-09-05"
---

# ADR-0154: The coordinated standard is not a relabel of existing v1 or v3

Status: accepted.

## Context

The estate already uses `1` and `v1` in several independent axes: HTTP `/v1`,
envelope `schema_version: 1`, hash domains `*:v1`, and older objects that were
never migrated. The provider kit and wire crate speak protocol 3
(`provider-v3`, kit `protocol_version` 3). Component scaffolds are at
`component-scaffold/6`. Treating any of those integers as "the standard" makes
an old envelope look like a new family and blocks release of a genuine
coordinated v1 (audit A10/A11).

## Options

1. Rename protocol v3 and kit `v3` to v1. Collides with existing envelope v1
   bytes and with already-published kit identity 0.2.10.
2. Relabel `component-scaffold/6` as `component-scaffold/1`. Collides with the
   historical `/1` golden that must remain validatable.
3. Introduce a separate family identity `ai-stp-standard/1` and a contract
   digest over a machine inventory of every axis. Keep HTTP `/v1`, protocol 3,
   and generator numbers as they are.

## Decision

Option 3. The coordinated family is `ai-stp-standard/1`. Classification uses
the `standard_family` key only. Other axes stay named as they are until a
deliberate incompatible family bump.

## Consequences

CLI `version` and `contract inventory` report the family and digest. New
scaffold writes record `standard_family`. Historical descriptors omit it.
Platform HTTP routes are unchanged; the inventory schema is CLI-only.
Renaming `provider-v3` remains out of scope.

## Revisit conditions

A coordinated 0.1.0 publication that must freeze the inventory digest into
released artifacts, or a proven need for the platform to persist
`standard_family` on published passports.
