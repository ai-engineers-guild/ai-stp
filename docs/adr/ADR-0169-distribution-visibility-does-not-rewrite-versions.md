---
description: "ADR-0169: Distribution visibility changes independently of immutable version passports."
last_verified: "2026-09-08"
---

# ADR-0169: Distribution visibility does not rewrite versions

Status: accepted

## Context

Owners upload privately by default and may later expose the same component to
everyone. Rewriting a sealed passport's visibility changes its digest and breaks
exact setup pins. Creating another version does not open the selected object.

## Decision

Server distribution visibility controls access independently of the passport's
historical visibility declaration. A separate owner plan binds exact version,
passport digest, prior and requested visibility, actor, device, expiry and effects.
Confirmation requires the exact hash and rechecks owner authority and prior
visibility. Passport, artifact, component graph and acquired copies are not rewritten.

A public response carrying a historically private passport explicitly declares
`distribution_visibility=public`. Legacy public passports remain readable without
that field; private passports without the assertion remain invalid anonymous catalog
responses.

New distribution plans default to private. Public exposure, including initial public
distribution, requires an explicit owner choice. A public setup cannot expose private
component pins; the platform checks this before effects.

## Consequences

Exact X.Y identities survive opening and later access changes. Revocation and closing
a version restrict future service access but cannot erase acquired copies. The
platform owner implements visibility state, authorization and projections. The CLI
provides plans and confirmation and refuses unsupported servers.

SPEC-071 owns acceptance; `docs/contracts/private-distribution.md` owns the wire boundary.
