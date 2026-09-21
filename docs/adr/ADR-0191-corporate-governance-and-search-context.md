---
description: "Use existing corporate authorization and catalog search for tenant governance context."
last_verified: "2026-09-18"
---

# ADR-0191: Corporate governance and catalog search context

Status: accepted. Extended by ADR-0193 for canonical corporate routing, bounded card
projections, technology-category filtering, and organization usage; extended by
ADR-0195 for effective assignment selection.

## Decision

Extend the existing Corporate Hub assignment table and catalog search contract.
Technology is an additional assignment subject; it is not a second assignment
store. Existing catalog ownership is extended with a typed owner coordinate for
the organization, team, project, technology, or employee while retaining the
employee field for compatibility. Governance relations are independently
persisted because maintainership, corporate verification, and lifecycle are
different facts. Each relation is tenant-keyed, revisioned, retained after
retirement/revocation, and mutated through the existing corporate `authorize()`
plus receipt/audit path.

Corporate catalog search is an optional context on the existing component/setup
search routes. It joins only authorized tenant projections and applies those
predicates before facet counts and page boundaries. Anonymous/public requests do
not load or infer corporate relations.

Technology category is an additional corporate facet sourced from the canonical
technology registry. Stable component/setup details expose readable related teams,
projects, and technologies as an organization-usage projection; the projection does
not create another assignment or governance store.

## Consequences

Existing global authorship, `author_verified`, `component_verified`, grants,
publication jobs, and harness installation remain untouched. Team-derived rows are
computed at read time from canonical team membership. Additive migrations and
generated contracts preserve old clients; application rollback hides new filters
and controls while retaining governance history.
