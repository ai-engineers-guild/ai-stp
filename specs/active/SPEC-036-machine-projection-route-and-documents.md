---
description: "SPEC-036: Addressable machine projection web and page machine documents."
last_verified: "2026-09-05"
---

# SPEC-036: Machine projection and machine documents

## Purpose

Web provides a machine representation of any page as a separate server
document at its own URL, so the agent receives the contents of the projection without
JavaScript, and a person can provide a link to it.

## Scope

Includes machine projection route, server mode definition, switch
projections, machine presenters of all routes, including private sections, machine
  object document, `/llms-full.txt` source, removal of the client projection
  provider and CSS filter.

Does not include CLI, passports, domain APIs, access rules and color theme
`light`/`dark` as an independent axis.

## Terms

- `Projection` - page projection: `human` or `machine`. Is the axis
  of representation and is not an access right.
- `Machine route` - own route segment `/{locale}/ai/{path}` with its own
  layout, returning the machine document of the page `/{locale}/{path}`.
- `Machine document` - structure of the machine representation of the page: headers with
  Markdown markers, Markdown links and text status fields.
- `Markdown link` - a link whose text contains both a label and an address:

  ```text
  [Catalog](/en/ai/catalog)
  ```

- `Presenter` - a page function that builds a `Machine document` from the same data,
  as the human representation.
- `Paired URL` - a pair of canonical and machine URLs for one page and locale.

## Requirements

- `REQ-3601`: The machine projection is addressed by the route `/{locale}/ai/{path}`.
  The server response to this URL contains the entire machine document, without execution
  JavaScript.
- `REQ-3602`: `Machine route` is a separate route segment with its own
  layout and does not rewrite the human path. Projections do not share route segments,
  therefore the shell of one projection cannot be shown with the content of another.
- `REQ-3603`: The projection is determined solely by the URL. It is not stored in
  `localStorage`, not set by client effect, not set by header
  request from the client and does not control `style.display` from the script.
- `REQ-3604`: Projection switch is a link to `Paired URL`, saves
  current path, query and locale, marks the active variant `aria-current` and
  works with JavaScript disabled. It is anchored at the bottom center of the viewport andis not included in the document flow.
- `REQ-3605`: Markdown in a machine document is DOM nodes. Headings,
  links and service markers are not created via CSS generated content and
  are present in `textContent`.
- `REQ-3606`: For each page, the machine representation text is different from
  human and contains at least one `Markdown link`.
- `REQ-3607`: Links within a machine document point to machine URLs of the same
  locale, so the projection is preserved across navigation without client state.
- `REQ-3608`: Machine page rendering, `/llms-full.txt` and
  `.md`-object representations are built by one presenter and do not contain
  independently written descriptions of a single object.
- `REQ-3609`: Domain presenters exist for landing, directory, page
  component of each of the closed types, setup page, exact version page,
  public profile, documentation, public legal documents, regional
  services, country and owner-workspace pages. Login forms and others
  static routes use a common page presenter.
- `REQ-3610`: The object's machine document contains a stable identifier,
  exact version, digest, harness, trust line, separate `author_verified` and
  `component_verified` and the CLI install command. Icons and decorative media in
  it is not included.
- `REQ-3611`: Machine representation has each route. Projection doesn't change
  page accessibility: private sections undergo the same session check and give
  the same redirect as in the human projection. Projection switch
  appears on all pages.
- `REQ-3612`: Machine-projected page never renders human
  tree, and the human page does not contain machine branches. Machine tree
  matches the path to the presenter via the route registry: domain presenter if
  it is there, otherwise the general document consists of the title, fields, records and links.
- `REQ-3617`: Navigation of both projections is built from one model: composition of points
  and their addresses are the same, only the presentation is different.
- `REQ-3618`: Within a machine document, only
  localized pages are rewritten into the projection. API endpoints, static machine surfaces and
  external URLs remain unchanged.
- `REQ-3613`: Styling the human tree with global rules for tags for needs
  of the projection is prohibited. Rules `.machine [data-machine-projection]`, interception
  of the `copy` event, and the client projection provider are removed.
- `REQ-3614`: Switching projection does not shift content: top coordinate
  `main` matches in both views of the same page.
- `REQ-3615`: Machine pages have full `ru` and `en` parity for visible ones
  strings, states and accessible names.
- `REQ-3616`: Canonical and machine pages link to each other
  `link rel="alternate"`, and the machine URL declares the human URL canonical
  URL of the same page.
- `REQ-3619`: Deploy-wide feature gate does not change projection parity: disabled
  The human surface and its machine pair both respond with 404 and are missing from the total
  navigation model (`SPEC-038`).
- `REQ-3620`: Content, contact and legal pages retain visible Human/Machine switch.
  It translates between `/{locale}/...` and `/{locale}/ai/...`, preserving the current locale
  route and query string; both projections are constructed from the same source of facts.
- `REQ-3621`: The machine document of a component is built by one presenter for all
  closed `component_type` values: `instruction`, `skill`, `mcp`, `hook`, `command`,
  `agent`, `plugin`, `setting`, `cli`. The `component_type` field is required and only
  accepts these values; icons and decorative media are not included in the document.
- `REQ-3622`: Machine route registry covers every human page
  `app` router. The pair is specified by `pattern`, access mode and feature/env gate;
  a page without a pair is a defect.
- `REQ-3623`: Presenter reads the same public facts and loaders as
  human page. Independently written description of the same object
  prohibited.
- `REQ-3624`: Query string of the paired URL is saved by the switch and sets
  the same list filters as the human interface: the directory applies the same
  parameters including `component_type`.
- `REQ-3625`: The machine document does not contain media address, `avatar`, `CSRF`,
  session token, secret and internal operation identifier, as well as
  decorative fields that are not found in the human facts of the same page.
- `REQ-3626`: Unknown path, disabled feature surface and missing
  object give the same 404 in both projections. Private pairs, including
  `publications`, `invitations`, owner and `staff` objects, keep one
  redirect to login.

## States and errors

`Machine route` for a nonexistent path responds with `404`, just like the canonical
path. `Machine route` for a private section without a session gives the same login
redirect as the human route and does not reveal content. An unknown `x-projection`
value is interpreted as `human`. Failure to build the machine document does not
degrade to a human page, but returns the page error while preserving the status code.

## Security and privacy

The page's machine document contains exactly the data that the same page shows in
human projection to the same subject. A public page is built only from the public
projection. Secrets, tokens, other users' private records, object-storage keys, and
internal operation identifiers do not enter the document. The `x-projection` header
is internal: a client-supplied value is not trusted and is overwritten by middleware.
Machine representation does not expand read permissions or bypass access checks.

## Compatibility and migration

Canonical page URLs do not change. Existing static machine
surfaces `/llms.txt` and `/agents.md` retain their addresses; `/llms-full.txt`
changes the source to presenters without changing the address or content type. The
The projection selection saved in the browser is no longer considered or migrated:
the URL becomes the source of truth. Rollback removes machine routes and the
switch, leaving canonical pages unchanged; passports, APIs, and data migrations are
not affected.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-3601` | A non-JavaScript request to `/{locale}/ai/catalog` returns `200` and machine text in the response body. |
| `REQ-3602` | Checking the route structure confirms the separate layout of the machine segment; browser check moves between projections without hydration warnings. |
| `REQ-3603` | Checking the server response finds `data-mode` matching the URL; Bundle search does not find projection entries in `localStorage`. |
| `REQ-3604` | The browser check with JavaScript disabled goes through the switch and confirms `aria-current` and the fixed position. |
| `REQ-3605` | The check finds `](` in the `textContent` of the machine page and does not find any matching `content` rules in the CSS. |
| `REQ-3606` | The browser check compares the `innerText` URL pairs for each page from `REQ-3609`. |
| `REQ-3607` | The browser check follows the machine document link and stays at the machine URL. |
| `REQ-3608` | The test compares the page document and the corresponding `/llms-full.txt` fragment from the common presenter. |
| `REQ-3609` | A parameterized test runs through a list of pages and requires a presenter. |
| `REQ-3610` | The object's machine document test checks for the presence of all listed fields and the absence of media. |
| `REQ-3611` | The browser check bypasses the list of routes and requires a machine document and a pinned switch on each; private URL pairs give the same redirect. |
| `REQ-3612` | The registry test checks for the presence of a route for each path and the absence of `readProjection` in human pages. |
| `REQ-3617` | The test compares a set of navigation items in both projections. |
| `REQ-3618` | The unit test verifies that API addresses and static surfaces are not rewritten. |
| `REQ-3613` | The static check confirms the absence of the `.machine [data-machine-projection]` rules, the `copy` hook file and the client provider. |
| `REQ-3614` | The browser check compares the top `main` coordinate on a pair of URLs. |
| `REQ-3615` | Locale parity checks occur for machine pages. |
| `REQ-3616` | Checking the server response finds `alternate` and `canonical` on both pages of the pair. |
| `REQ-3619` | Scenario of two compiled profiles checks the same 200/404 human and machine routes. |
| `REQ-3620` | Playwright verifies paired URLs and the switch on content, contact and legal pages. |
| `REQ-3621` | The parameterized unit test builds an object document for each of the eight `component_type` and requires a `component_type` field without media. |
| `REQ-3622` | The unit test compares inventory with each `page.tsx` of the human tree and with `MACHINE_ROUTE_PATTERNS`. |
| `REQ-3623` | The unit test checks that catalog/object/country/service presenters accept facts from the same loaders as human pages. |
| `REQ-3624` | The unit test applies the catalog query to the machine presenter; Playwright saves the query in the Human/Machine switch. |
| `REQ-3625` | The unit test rejects media, avatar, CSRF, secret and internal identifiers in the serialized document. |
| `REQ-3626` | Playwright requires the same 404 on an unknown path and the same login redirect on private pairs; feature-profile scenario preserves 200/404 parity. |
