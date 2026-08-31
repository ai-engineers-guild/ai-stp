---
description: "Decision to store the external service and countries as mutable catalog metadata outside the passport."
last_verified: "2026-08-12"
---

# ADR-0088: External products as catalog metadata

Status: accepted.

## Context

A component or setup may automate Kaspi, 1C, Notion, and other external
services. This relationship is needed for discovery by service and country, but
does not change the bytes, provenance, or digest of the published version.

## Decision

`ExternalProduct` is stored separately from the passport and deduplicated by a
unique registrable domain. The primary URL allows only `HTTPS`, a public DNS
name, and no more than one path segment; userinfo, credentials, and IP literals
are prohibited, while query parameters and fragments are discarded. A small
pinned list is used for common compound public suffixes, with no runtime PSL
dependency.

Countries are represented by an M:N table and validated against the ISO 3166-1
alpha-2 list pinned in code. Web builds localized country names through
`Intl.DisplayNames`. Only the owner may change the relationship with
`CatalogMetadata`, and only through the Web API; the CLI and passport do not
gain corresponding fields. Public service and country pages read only
active/public/published objects. The section can be hidden with
`NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED=false` while preserving the data.

## Consequences

The decision requires neither Flagsmith, LaunchDarkly, a PSL package, nor a
country API. The small suffix allowlist is conservative: a new regional suffix
is added together with a test. Product creation remains authenticated and
returns a conflict for an occupied domain or a normalized name match.

## Reconsideration conditions

The decision is reconsidered if the catalog requires the full PSL, a moderation
queue, logo uploads, or independent object-level relations instead of a
projection of all versions of one stable object.
