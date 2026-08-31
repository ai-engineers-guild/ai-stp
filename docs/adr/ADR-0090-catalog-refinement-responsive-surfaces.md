---
description: "Decision to establish catalog-refinement UX invariants instead of rigidly choosing modal/drawer."
last_verified: "2026-08-14"
---

# ADR-0090: Responsive catalog-refinement surfaces

Status: accepted.

## Context

The catalog gained fast text search, structured filters, sorting, a view
selector, and regional relationships. In the existing Web UI, some controls
were full searchable multiselects and expandable panels, while some later
requirements began prescribing a specific widget: a centered modal or drawer.
This created a conflict between the specification and the product objective.

The product invariant is different: users must refine results without losing
context, the URL, keyboard accessibility, or the result set. The specific shell
depends on screen width, content density, and the number of active filters.

## Options

1. Always use one modal dialog. It is easy to test, but on desktop it separates
   users from results and duplicates existing working multiselects.
2. Always use inline panels. This works well on desktop, but on a narrow viewport
   quickly turns the catalog into a long page of filters before the results.
3. Establish behavioral invariants and allow a responsive surface: a
   docked/attached panel on a wide screen and a contained overlay/sheet/drawer on
   a narrow one, with identical controls and URL semantics.

## Decision

Option 3 is selected. Normative catalog specifications describe not a specific
component but the required properties of the `refinement surface`:

- desktop may show refinement as an inline, docked, or attached panel next to
  the hero/search area if results remain available without a reload;
- a narrow screen uses a contained modal surface: sheet, drawer, or dialog with
  an explicit `Close`, closing on `Escape` and backdrop, focus trapping, and
  focus return to the opening button;
- every variant uses the same searchable multiselect, date range, sorting, and
  view selector; the surface does not replace filters with simplified one-off
  lists;
- `Reset all`, `Apply`, active-value chips, validation errors, and help are
  available regardless of the chosen shell;
- changing search, filters, sorting, page mode, or view mode updates the URL and
  refetches only the catalog without reloading the entire shell;
- Catalog QL autocomplete and simple correction are opt-in/contextual assistance
  and do not rewrite ordinary text such as `author` or `tags` into reserved
  keywords without an explicit user choice.

## Consequences

- `SPEC-034` and `SPEC-037` must no longer require a specific `modal dialog`
  where a responsive refinement surface is needed.
- Component/a11y tests verify surface properties: accessible name, opening,
  closing, keyboard behavior, URL preservation, identical controls, and no full
  page reload.
- Visual implementations may change without a new ADR as long as the described
  invariants are preserved.

## Reconsideration conditions

The decision is reconsidered if a single design-system primitive for complex
filters becomes mandatory for all product surfaces, or if the catalog moves to
server-driven UI where the filter container becomes part of the contract.
