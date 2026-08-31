---
description: "Decision: the web machine projection is an addressable server route and a separate document."
last_verified: "2026-08-10"
---

# ADR-0076: Machine projection as an addressable route

Status: accepted.

## Context

The public web has two projections: `human` and `machine`. The current rule is
recorded in `docs/product/DESIGN.md` and describes machine as a format change
within a single React tree. The implementation follows this rule: a client-side
provider adds the `.machine` class to `<html>`, stores the selection in
`localStorage`, and imperatively hides headers, while the machine presentation
is assembled entirely from CSS generated content in
`apps/web/src/app/globals.css`.

Measurements on the running environment show that this projection does not
produce a machine-readable result:

- the `main` text on `/en/catalog` is byte-for-byte identical before and after
  switching (1620 characters), so the content does not change;
- the server response contains neither the `.machine` class nor
  `data-projection` nor machine text, so the first frame is always human, while
  `curl` and crawlers never see the machine projection;
- the Markdown presentation of links and headings exists only as `::before`
  and `::after`, while generated content is absent from the DOM, `textContent`,
  `innerText`, view-source, and every network response;
- the `machine:` variant is used six times in the application, all six in the
  shell, so pages make no substantive projection decisions;
- global tag-based rules conflict with the production layout: the
  `a[href]::after` rule occupies the same pseudo-element as the stretched link
  `after:absolute after:inset-0` in a catalog card and prints the URL over the
  card.

A direct consequence of machine text being absent from the DOM is the `copy`
event interception that fabricates Markdown in the clipboard. This indicates
that the tree contains no data for a machine.

Reference implementations confirm a different approach. `parallel.ai` serves
machine through a separate `/ai` route, keeps the mode in `data-mode` on the
wrapper, stores both representations in the DOM, and makes about 223 visibility
decisions through the `machine:` and `not-machine:` variants. `nace.ai`
replaces the page tree with a separate machine document in which Markdown is
represented by actual DOM nodes, and the text volume grows from 1595 to 4318
characters due to a site index and dense technical lines.

## Options

1. Keep the CSS filter and fix conflicts individually. This is inexpensive but
   does not eliminate the cause: the content does not change, the mode is not
   addressable or visible to the agent, and each new utility class creates a
   new conflict.
2. A second client-side tree without a route. This provides real machine text
   but retains `localStorage` as the source of truth, leaves a flash of human
   content during loading, and provides neither a link, SSR, nor indexing.
3. An addressable route and a second server-side representation. This requires
   more work and moves some pages to dynamic rendering, but provides SSR, a
   link, indexability, verification through `curl`, and removes client-side
   state.

## Decision

The machine projection is a separate server-side representation of a public
page, addressable through its own URL.

The mode is determined by its own `/{locale}/ai/{path}` route segment. This is
a real App Router segment, not a rewrite of the human path: the human tree
lives in the `(site)` route group, the machine tree in `ai`, and each has its
own layout. There is no middleware rewrite. The client-side projection
provider, `localStorage`, and imperative `style.display` management are
removed.

The rewrite was rejected for a mechanical reason. With a rewrite, both
projections resolve to the same segments, while Next.js reuses the segment's
cached layout during client-side navigation and leaves the canonical URL
unchanged. This produced the shell of one projection with the content of the
other, a hydration mismatch, and a crash on a null `parentNode`. Separate
segments eliminate the cause, not the symptom.

The machine tree owns its content. A route registry maps a page path to a
presenter that returns a machine document from the same domain loaders as the
human page. One presenter serves three consumers: the machine page,
`/llms-full.txt`, and an object's `.md` representation. Markdown is represented
by actual DOM nodes. Human pages contain no machine branches: the projection
does not branch within a page; it lives in its own tree.

Navigation for both projections is built from one model: the human header
renders it as links and the machine header as Markdown links, so their item
sets do not diverge. Links in the machine document lead to machine URLs, while
non-page addresses—API endpoints, static files, and external URLs—are never
rewritten.

The projection switch is a link to the paired URL and works without JavaScript.
Machine links inside the machine document lead to machine URLs, so the mode
persists across navigation without client-side state.

Global tag-based styling of the human tree is prohibited. The
`.machine [data-machine-projection]` block and `copy` interception are removed.

Every route has a machine representation. The projection changes only the
presentation form and never changes page availability: private sections
undergo the same session check as in the human projection and produce the same
redirect when it is absent. The switch is present on every page and does not
disappear beneath the user during navigation.

## Consequences

The machine tree is rendered dynamically; the human tree retains its previous
caching modes because it no longer reads the projection. This creates an
obligation: a new page receives a machine presenter in the same change. A page
without a presenter is a defect, not an allowed state: the machine route is not
replaced with a human copy and does not disappear from navigation.

`/llms-full.txt` ceases to be a separate hard-coded text and is assembled by
the same presenter, eliminating divergence between what the agent sees and
what is published.

Rollback removes the entire `ai` segment: machine URLs cease to exist, the
switch is hidden, the human tree is unaffected, and passports, API, and data do
not change.

Checks cease to be cosmetic: they require proof of a substantive difference
between representations, the presence of machine text in the server response
without JavaScript, and the absence of layout shift when switching.

## Reconsideration conditions

The decision is reconsidered if a normative external format for the machine
representation of a page emerges and makes a dedicated presenter redundant; if
the share of public pages with a machine document is below one half two releases
after implementation; or if dynamic rendering of the public catalog ceases to
meet response-time requirements.
