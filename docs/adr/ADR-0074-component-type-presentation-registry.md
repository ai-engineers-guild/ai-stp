---
description: "Client-side presentation registry of component types and the media migration path."
last_verified: "2026-08-09"
---

# ADR-0074: Presentation registry of component types

Status: accepted.

## Context

The catalog must make it possible to instantly distinguish `instruction`, `skill`, `mcp`,
`hook`, `command`, `agent`, `plugin`, and `setting`. These types are currently
a closed contract enum, while simple UI icons are not part of
passports. Requesting a separate image when rendering each row would reduce
reliability and provide no benefit with a closed list.

## Decision

Until a managed catalog of types appears, web owns the exhaustive presentation
registry. It maps each contract identifier to one SVG icon from a shared
stroke system and localized `ru`/`en` names. The registry is checked for
completeness against the contract enum. Domain logic, search, and passports do not depend
on it.

When the list becomes manageable without a client release, the type metadata
(`id`, localized names, accessibility label, media revision) moves to
PostgreSQL. Versioned binary image variants are stored in
S3-compatible object storage; the database stores only the content-addressed reference,
dimensions, and MIME. The client receives an allowlisted manifest, caches it by revision, and
retains the built-in registry as an offline/failure fallback.

## Consequences

The current UI makes no network requests for pictograms and does not display emoji or
letter placeholders. Adding a new contract component type requires updating the
registry and both locales in the same change. The future migration does not change type
identifiers and does not make object storage the source of domain truth.
