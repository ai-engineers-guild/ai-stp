---
description: "The Corporate Hub extends one catalog and one authorized directory projection."
last_verified: "2026-09-18"
---

# ADR-0193: One corporate catalog and directory projection

Status: accepted. Extends ADR-0190 for operational-owner presentation and ADR-0191
for canonical corporate catalog routing, category context, and organization usage.

## Context

Corporate components have a second route and filter implementation beside the catalog.
Root directories and nested detail sections shape the same entities differently, and
some Web loaders materialize every backend page. The duplication causes missing owner
and lead labels, inconsistent actions, unbounded reads, and route-specific fixes.

## Options

1. Continue independent route, loader, card, and relation implementations.
2. Build a new corporate-only catalog and replace the existing catalog.
3. Extend the existing catalog with optional authorized corporate context and use one
   server-owned card projection for root and nested corporate directories.

## Decision

Choose option 3. `/corporate/catalog` is the only corporate setup/component catalog.
Corporate facets extend the existing search contract and are applied before totals,
facets, sorting, and pagination. `/corporate/components` is a compatibility redirect.

One bounded server projection supplies corporate directory and nested relation cards,
including readable identity, relationships, category, and available actions. Web
directories request one page and keep query state in the URL. Stable catalog object
routes are navigation targets; exact versions remain assignment facts rather than page
identity.

## Consequences

The Web reuses incumbent catalog cards, filters, Markdown renderer, media gallery, and
searchable selectors. The API owns enrichment and authorization-before-count. New job
title and technology-category facets extend generated contracts. Redirects, query
translation, public compatibility, tenant isolation, and root-versus-nested projection
parity require executable tests. Application rollback hides corporate facets and may
restore legacy handlers without deleting governance data.

## Revisit conditions

Revisit if corporate catalog objects acquire a publication or identity model that is
incompatible with the public catalog, or if measured directory scale requires a cursor
contract that offset pagination cannot satisfy.
