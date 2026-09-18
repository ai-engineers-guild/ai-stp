---
description: "ADR-0188: Corporate build isolation and tenant-scoped presentation ownership."
last_verified: "2026-09-18"
---

# ADR-0188: Corporate workspace presentation boundary

## Status

Accepted. Clarified by ADR-0192 for account-backed employee identity and ADR-0193
for the canonical catalog and directory projection.

## Context

The Corporate Hub redesign requires a distinct build surface, authorized directory
and hierarchy projections, designated ownership separate from authorship, and rich
entity presentation editing. Existing competence and responsibility relations do
not grant that editing authority. Existing personal public profiles are not a safe
place to store private organization media.

## Decision

Corporate builds exclude personal editorial, regional-service, Company, and Legal
routes and navigation. Personal SaaS retains its current surface; local context
does not deploy a website. Corporate workspace destinations live under `/corporate/`.
The corporate Next build enables the native `skipMiddlewareUrlNormalize` setting
to preserve this route boundary; public SaaS and self-hosted builds leave it off.

Introduce explicit tenant-scoped presentation and ownership data. Preserve all
existing stable IDs and retained relations. Ownership does not rewrite authorship,
competence, project use, verification, installation state, or visibility.

Authorize presentation editing through current same-tenant administrator, team-lead,
or technology-owner authority as specified by SPEC-083. Team-lead cross-entity
presentation editing does not imply cross-entity administration. Existing scoped
RBAC remains authoritative for access/security changes. Every write still checks
anchor access, current authorization/object revisions, and durable idempotency.

Reuse profile UI/storage primitives only behind corporate authorization and media
isolation. Validate content and references server-side. Directory/Overview queries
authorize every included object before computing names, tags, and counts. Repeated
tree nodes are projections, never additional membership or assignment records.

## Consequences

Roll out additive storage and generated contracts before API and Web. Test denied
and hostile-tenant reads/writes, owner/lead editing, media references, and build route
exclusion. Application rollback disables new operations and preserves presentation,
media, owners, receipts, identities, and audit history; it does not drop volumes.
Administration and Landscape retain their incumbent implementation and visual world.

Normal lifecycle values are retained as domain facts but are not required decoration
on ordinary cards and headers. SPEC-086 owns the shared detail frame, exceptional-state
presentation, Markdown table, gallery, and responsive acceptance behavior.
