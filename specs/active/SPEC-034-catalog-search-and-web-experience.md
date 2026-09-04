---
description: "SPEC-034: Powerful catalog search, compact web UX and media profile."
last_verified: "2026-09-04"
---

# SPEC-034: Catalog search and web experience

## Purpose

The public catalog provides a compact bilingual interface, strict structural
search and predictable pagination, and landing, object pages and profile
use one accessible design system and reliable media flow.

## Scope

Includes landing and shell, catalog of components and setups, query language, filters,
sorting, card/list presentation, web pagination counters, object pages,
public profile, avatar upload and secure Markdown. The CLI retains cursor mode.
Browser editor setups and arbitrary HTML are not included.

## Terms

- `Catalog QL` - a limited language of logical expressions over allowed fields.
- `Page mode` — web pagination with page number and exact total for the current one
  public cut.
- `Cursor mode` - stable keyset pagination without total expansion.
- `Refinement surface` - responsive shell for search, filters, sorting and
  selecting a view; the specification defines behavior and accessibility, not a
  specific widget.
- `Verified only` - both `author_verified=true` and
  `component_verified=true`; one axis does not replace the other.

## Requirements

- `REQ-3401`: The authenticated landing page does not show `Sign in`; the header does not
  show a sign-out action and uses an icon profile menu. Navigation has
  localized keyboard-accessible tooltips.
- `REQ-3402`: Landing hero uses a large brand mark, a canonical slogan and
  autoplay-muted-loop preview with poster/fallback and reduced-motion mode.
- `REQ-3403`: App shell keeps footer at the bottom edge of a short page and does not
  overlaps the contents of a long page.
- `REQ-3404`: Search toolbar is minimized to one button by default; condition
  expands without losing the query URL and does not occupy a permanent large area.
- `REQ-3405`: Resource, tags, harnesses, component types and authors are
  searchable multiselect filters. `Verified only` and the last one
  `Include experimental` are checkboxes. Each filter has a separate
  accessible help.
- `REQ-3406`: Structured refinement opens upon request in responsive
  refinement surface. On desktop, inline/docked/attached panels are acceptable if
  results remain available without a reload. On a narrow screen, the surface
  is a bounded modal surface with an explicit `Close`, closing via
  `Escape` and backdrop, holding focus and returning focus. Surface uses
  the same searchable multiselect, date range, sorting and view selection,
  shows `Reset all`, `Apply`, chips of active values, validation errors and
  help.
- `REQ-3407`: Sorting is separated from filters and supports `relevance`,
  `updated_at` and `likes`, and the `asc` / `desc` direction is applied by the server before
  page boundary. The direction is included in the signature of the cursor request to continue
  could not be applied to another sort. Each sort has a stable tie-breaker;
  Flipping only the current page on the client is prohibited.
- `REQ-3408`: Catalog QL supports plain text, `NAME`, `TAGS` fields,
  `HARNESS`, `TYPE`, `AUTHOR`, `VERIFIED`, operators `AND`, `OR`, `NOT`, `IN`,
  `NOT IN`, `:` and parentheses. Backend is the final validation boundary;
  frontend returns a compatible early error with position. Autocomplete and
  simple correction are opt-in/contextual assist and do not rewrite
  plain-text query in reserved keywords without explicit user selection.
- `REQ-3409`: Parser builds bounded typed AST and never interpolates input into
  SQL. The length, number of tokens, depth and size of `IN` are limited.
- `REQ-3410`: Web page mode returns `total_items`, `total_pages`, current
  page and bounded navigation: edges, current neighborhood and gaps, not all
  pages as separate controls. Cursor mode remains opaque and does not mix
  with page mode.
- `REQ-3411`: Results have card/list view. The entire entry is clickable, the author has
  separate link, information is not duplicated, image depends on object/type.
- `REQ-3412`: The object page has a compact header, a back button and a type icon,
  localized dates and responsive metadata layout without excessive indentation.
- `REQ-3413`: Account shows `Edit profile` and `View public profile`; avatar
  goes through upload, validation, object storage, linking to draft, publishing, and
  refresh, but the original does not become public.
- `REQ-3414`: Safe Markdown supports headings, GFM tables, Unicode emoji and
  annotated inline links, prohibiting raw HTML and dangerous URL schemes.
- `REQ-3415`: All visible lines, states, tooltips, accessible names, dates and
  landing/catalog/detail/account errors have full `ru`/`en` parity.
- `REQ-3416`: Interactive elements have semantic selectors; `data-testid`
  only used when role/name is insufficient.
- `REQ-3417`: Anonymous catalog reads only non-negative aggregate
  `likes_count`; sorting by it is stable. Recording individual reactions and
  expansion of account IDs is not included in this specification.
- `REQ-3418`: Web stores a comprehensive presentation registry of component types:
  a stable identifier, a simple distinguishable icon, and a localized name.
  The registry is not a domain source of truth. When managed types appear,
  metadata moves to PostgreSQL and image versions to S3-compatible object
  storage per `ADR-0074`.
- `REQ-3419`: The object and exact version page shows `View Source` only for
  valid GitHub origin and leads to pinned `commit + subpath`, not to
  moving branch or unverified external URL.
- `REQ-3420`: The share button on the object page passes the native Web Share API
  canonical URL of the exact version and copies the same URL to the clipboard if the API
  unavailable or ended with a technical error.
- `REQ-3421`: Detail page shows the requirements of the exact version in a structured way:
  names and purpose of env without values, need for credentials/authorization,
  declared permissions and external endpoints; setup shows the passport aggregate.
- `REQ-3422`: Catalog read uses the current account-level `author_verified`, and
  the card shows it with an avatar ring and a check marker regardless of the content check.
- `REQ-3423`: GitHub stars are read from a separate mutable cache by provenance
  repository, is updated by a worker using ETag and bounded backoff, hidden when
  no value and never affect trust.
- `REQ-3424`: Web receives explicit consent `accept/reject/manage` for analytics and
  marketing, stores the choice in a first-party cookie, and optional integrations remain
  turned off until consent; necessary cookies are not disabled.
- `REQ-3425`: External products and services are mutable metadata
  views, deduplicated by registered domain, have a main URL
  `HTTPS` no more than one segment deep, list of countries `ISO 3166-1 alpha-2`
  from a reference book fixed in the code and a many-to-many relationship with versions
  catalogue. IP literals, userinfo and credentials are prohibited; query and fragment
  are removed. Service creation and attach/detach are available only through the owner Web API;
  CLI passports do not accept them. Public Web provides `/services/{domain}`
  and `/countries/{code}`; the entire section is disabled by the feature flag without deleting the data.
  A public overview of countries and services distinguishes the selected state, shows
  country not only by ISO code and gives a transition to a directory with already applied
  filters. Sentinel `unspecified` depends on facet: service facet means
  an object without an associated service, country facet is an object with an associated service
  no country; between service/country facets `AND` is valid, inside facets - `OR`.
- `REQ-3426`: Component and setup card in list and cards keeps readable
  title and action area: the author profile does not displace the title and menu.
  The author remains a separate link with an avatar and `author_verified`, if any.
  `likes_count` is visible in both views; GitHub stars only if the value
  available. A missing metric is not shown as zero. In the center -
  relative total security checks; `warning`, `failed` and `not-run` remain
  visible. If there is risk data, the card adds a short reason
  open the post and does not confuse author attribution with content security.
- `REQ-3427`: `VerifiedAvatar` is the only author tag component: thin
  round outline, small checkmark at the bottom edge, no overlapping photo or
  reserve character, no line height change, no name shift and no
  local negative displacements. Catalog, object page and public
  profile use the same component for the photo and the spare sign.
- `REQ-3428`: The vertical menu of the three points of the card contains Copy URL, Copy ID,
  Copy CLI command, separator and Report component or Report setup. Clipboard feedback,
  keyboard control, Escape closing, and focus return are provided. The main card actions
  are not duplicated. Report opens
  existing complaint flow.
- `REQ-3429`: Directory lookup accepts optional `updated_from` and
  `updated_to` as calendar dates `YYYY-MM-DD`. One or both edges are acceptable,
  clear range, chip each active edge, Reset all, save to URL and
  client navigation without a full reboot. UTC semantics belongs to
  `docs/contracts/http-api.md`: the lower limit is the beginning of the specified day, the upper limit is
  the beginning of the next day; the reverse range is `AI_STP_VALIDATION_ERROR`. Signature
  the cursor includes the specified dates; empty bounds are omitted from the signature, so
  old URLs remain valid. Component and setup use one
  contract.
- `REQ-3430`: The directory has an explicit Both/All mode along with `components` and
  `setups`. Both uses one contiguous list with no separate sections:
  setups come first, then components; the selected sorting is preserved within each type.
  The type is distinguished within the row itself. Old values
  `resource=components` and `resource=setups` don't break. Web requests two
  independent projections and preserves their page boundaries in the URL, but does not turn them into
  two visually independent outputs. While setup pages remain, component rows do not
  precede them; the first component page is appended to the last setup page,
  subsequent component pages continue the same list without repeating setups.
  Filters only apply to
  the corresponding object type.
- `REQ-3431`: Search `q` is trimmed. A blank or whitespace-only `q` is absent:
  it does not become a distinct match-all query and is omitted from the cursor
  signature the same way a missing `q` is.
- `REQ-3432`: Multi-value filters are trimmed, de-duplicated, and sorted before
  matching and before the cursor signature. Singular `harness_id` and
  `component_type` merge with `harness_ids` and `component_types` using OR.
- `REQ-3433`: Latest public version selection, structural filters, relationship
  filters, Catalog QL, relevance ranking, `updated_at` and `likes` sorts, page
  totals, and keyset pagination execute as parameterized SQL against one search
  projection. Cursor keys are the selected sort keys plus `stable_id`.
- `REQ-3434`: The search projection is one row per `(object_kind, stable_id)`
  for the latest public `X.Y`, written in the publication transaction, with a
  deterministic rebuild. It does not relax trust, lifecycle, or public
  visibility rules.
- `REQ-3435`: There is no production special case for `q=pytest` or any other
  fixture needle. A term matches stored name, description, identifiers, tags,
  or vocabulary aliases only.
- `REQ-3436`: The closed tag vocabulary is one versioned source exposed as an
  anonymous machine-readable API. Passports and tag filters use canonical ids;
  search also matches names and aliases. Duplicate tag identifiers are
  rejected.
- `REQ-3437`: Catalog QL recognizes fields and operators only in unquoted word
  tokens. Single- or double-quoted `AND`, `OR`, `NOT`, `IN`, and field names are
  literal search text. The local evaluator and PostgreSQL search both use
  case-folded word-token matching for plain terms.
- `REQ-3438`: The catalog search control identifies fields and operators in
  autocomplete, displays a live syntax-highlighted preview, and provides
  localized field/operator reference and quoting guidance. The input remains a
  native keyboard- and screen-reader-operable combobox.

## States and errors

QL errors contain the stable code, position and expected token class. Invalid
filter/sort/page is rejected rather than ignored. Incompatible `cursor` and `page`
produce a validation error. Upload distinguishes unsupported format, excessive size,
processing, storage failure, and readiness. The UI preserves the applied URL on a network error.

## Security and privacy

Search works only on the public projection and does not reveal hidden/private
count. `total_items` only refers to an already resolved public slice.
QL is compiled only from allowlisted AST. Avatar is checked by MIME and bytes;
the original is private. Markdown sanitization prohibits raw HTML, scriptable URLs and
event handlers. Like does not expand the list of account IDs.

## Compatibility and migration

Existing component and setup routes, as well as cursor parameters
are saved. The page mode is added explicitly and does not change the semantics of the response
cursor. Old single filters are accepted as a list of one value and
are normalized along with the list parameters to the search and cursor signature.
Singular `harness_id`/`component_type` and their list forms share one OR set and
one signature. Meaning
`resource=both` is accepted as a general mode. URL without `updated_from` and
`updated_to` keep the previous output. Cursors that lack sort keys are rejected
as an unsupported version. Rollback drops the search projection and restores
the previous scan only by reverting the change; published passports stay.

## Acceptance criteria

| Requirement | Executable oracle |
| ---------- | -------------------------------------------------------------------------------- |
| `REQ-3401` | Component verification distinguishes between anonymous and authenticated headers.                                |
| `REQ-3402` | Browser check sees the logo, slogan and autoplay preview.                                    |
| `REQ-3403` | Checking the two viewport heights confirms the position of the footer.                                      |
| `REQ-3404` | Component verification confirms the collapsed search and expansion with a button.                          |
| `REQ-3405` | Component checking covers all types of filters and help.                                     |
| `REQ-3406` | Component/a11y tests confirm responsive refinement surface, identical controls, reset/apply, close, focus containment to narrow and saving URL without full reload; `mobile-public-smoke.spec.ts` confirms keyboard/focus refinement at 360 and 430 px in `ru` and `en`. |
| `REQ-3407` | The API unit test confirms the stable sorting of the three modes.                                   |
| `REQ-3408` | Parser tests cover all fields, statements and error positions; component tests - opt-in autocomplete/correction without rewriting plain text. |
| `REQ-3409` | Property tests check length, token, depth, and IN bounds.                                   |
| `REQ-3410` | API tests check totals and page incompatibility with cursor; component tests - bounded page window and lack of unbounded DOM controls. |
| `REQ-3411` | Component checks cover card/list and author links.                                       |
| `REQ-3412` | Browser check confirms compact responsive detail page; `mobile-public-smoke.spec.ts` confirms 360/430 px in `ru`/`en` without document-level overflow and with visible install/view CTA. |
| `REQ-3413` | The script executes upload → draft → publish → public read.                                       |
| `REQ-3414` | Golden/XSS tests cover tables, headers, emoji and links.                                   |
| `REQ-3415` | i18n parity and locale E2E pass for modified pages.                                        |
| `REQ-3416` | The availability check finds controls by role and name.                                            |
| `REQ-3417` | Projection/API tests prove public aggregate and stable sorting.                       |
| `REQ-3418` | Component test goes through all contract component types and finds icon and localizations `ru`/`en`. |
| `REQ-3419` | Unit tests check exact commit/subpath and reject moving or spoofed URLs.             |
| `REQ-3420` | Component test checks the native share of the exact version-scoped URL and clipboard fallback.           |
| `REQ-3421` | Component test checks for structured requirements and absence of secret values.            |
| `REQ-3422` | Platform unit test checks the current-state overlay, component test checks an independent avatar marker.  |
| `REQ-3423` | Worker unit tests check URL, ETag/cache; card test separates stars from trust.                  |
| `REQ-3424` | Unit/component tests check persistence, reject and the absence of optional consent by default.   |
| `REQ-3425` | Unit/API tests check URL policy, domain conflict, owner-only mutation, country roof with objects, two `unspecified` values, `AND` between facets and `OR` inside facet; migration tests - M:N schema; component test - the selected state, the difference between the country and the bare code and catalog CTA with filters. |
| `REQ-3426` | Component tests cover card/list, author outside title/action, likes in both types, available stars, no false zero, why-open and visible warning/failed/not-run. |
| `REQ-3427` | Component test checks the stroke, check mark at the edge, photo and placeholder, constant line size and the absence of negative offsets. |
| `REQ-3428` | Component test checks menu composition, clipboard, Escape, keyboard, focus return and separate Report titles. |
| `REQ-3429` | Parser/API tests cover single edge, full range, reverse range, UTC bounds and cursor signature; web test - chip, reset and URL. |
| `REQ-3430` | Component/unit tests confirm one list, setups then components order, no group sections, independent type sorting, old resource values ​​and bounded page boundaries. |
| `REQ-3431` | API/unit tests treat whitespace `q` as absent and share the empty-query cursor signature. |
| `REQ-3432` | Unit tests prove singular+list OR merge, unique sorted multi-value filters, and identical cursor signatures for equivalent forms. |
| `REQ-3433` | Integration tests walk every sort in cursor mode without duplicates or skips and compile typed QL to SQL; page mode still returns totals. |
| `REQ-3434` | Migration and rebuild tests keep one latest row per object, including out-of-order `X.Y` publication. |
| `REQ-3435` | A `q=pytest` probe does not match `fixture-component` unless that needle is in stored text, tags, or aliases. |
| `REQ-3436` | Contract/API tests serve the versioned vocabulary; alias search hits canonical tags; duplicate tags are rejected. |
| `REQ-3437` | Parser tests cover quoted reserved words, quoted field names, predicate values, escapes, and evaluator/SQL word-token parity. |
| `REQ-3438` | Component tests cover categorized autocomplete and syntax preview; RU/EN messages explain quoted literals. |
