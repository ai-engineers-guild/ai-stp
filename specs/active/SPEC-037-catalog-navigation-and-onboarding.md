---
description: "SPEC-037: Compact catalog, owner/public navigation, and CLI onboarding."
last_verified: "2026-08-17"
---

# SPEC-037: Catalog, Navigation, and CLI Onboarding

## Purpose

The catalog remains fast and easy to understand: search is always visible, filters do not occupy
page space, and applied constraints are clear and reversible. The owner can safely
navigate between their object workspace and the public view, while empty screens explain
the next action through the CLI.

## Scope

Included: refining results without losing the search query, chips, reset, help guidance,
selecting multiple tags, owner/public navigation, copying CLI commands, and empty states. Excluded: a browser-based
passport editor, client-side authorization, recommendations, and hidden filters.

## Terms

- `Owner view` — the authenticated projection of objects belonging to the current account.
- `Public view` — the anonymous projection of the published catalog.
- `Applied filter` — a filter in the URL applied by the server contract.
- `Refinement surface` — a responsive container for additional result constraints;
  the container may differ by viewport, but its controls and semantics are identical.

## Requirements

- `REQ-3701`: The catalog hero contains exactly two compact icon buttons:
  text search and filters/sorting. The result type selector (`components`,
  `setups`, Both/All) is located in the filters panel. Additional constraints
  open on request, do not occupy permanent page space, and do not displace
  results on a narrow viewport: the user sees the same controls, can close
  the refinement surface using the keyboard, and sees the number of filters already applied.
  The implementation is not required to use one specific `modal`/`drawer`, but it must
  preserve the searchable multiselect and date/sort/view controls from the current
  contract.
- `REQ-3702`: The tag filter supports all values permitted by the contract, not
  only the first tag. Applied filters are displayed as dismissible chips and
  serialized in the URL without losing order or duplicates; `Reset all` restores
  the contract defaults.
- `REQ-3703`: The help element next to the filters explains every filter, trust lines,
  request-scoped experimental consent, cursor pagination, and page-mode totals, when
  available. It is a semantic button/dialog with keyboard/focus support, not a
  hover-only tooltip.
- `REQ-3704`: Experimental consent remains a separate explicit request and is not
  stored as an indefinite preference. The UI does not mix experimental results with
  authoritative results.
- `REQ-3705`: An owner version with a public state displays `View public page`; a public
  object/version page displays `Manage this version` only to the authenticated
  owner. Private drafts use owner preview routes rather than public links.
- `REQ-3706`: The catalog and owner pages provide a copy action for exact CLI commands
  (`registry show` for a public object/version and an owner-appropriate next step)
  and obtain the command template from a single canonical source. The UI does not promise browser installation.
- `REQ-3707`: Empty owner objects/access/publications states explain that
  passports and setups are created through the CLI/agent, provide a copyable safe command and a link to
  the documentation. They do not display a nonexistent browser editing function.
- `REQ-3708`: Mobile primary navigation has a menu/drawer and does not hide signed-in
  routes without an alternative. The active route, current state, and keyboard focus are visible.

## States and errors

An invalid URL filter receives the current typed validation state without being silently
dropped. A network error preserves the visible applied filters and offers a retry. Copy
failure reports the outcome without falsely indicating success. If the lifecycle changes,
an owner/public link displays a safe not-found/error state.

## Security and privacy

URLs, chips, and help do not disclose private IDs, consent, or the existence of private
objects. Owner navigation is verified by the API/server session, not by a hidden button.
CLI commands escape arguments and contain no token, local path, or secret.

## Compatibility and migration

Existing query parameters retain their meaning. The new UI does not decode the cursor;
the filter form belongs to the current OpenAPI contract. Help text is localized and does not
duplicate the normative rules of the trust model.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-3701`–`REQ-3703` | Component/a11y tests cover the responsive refinement surface, opening/closing on a narrow viewport, chips, multiple tags, preservation of searchable controls, and Reset all; `mobile-public-smoke.spec.ts` verifies keyboard/focus behavior at 360 and 430 px in `ru` and `en`. |
| `REQ-3702` | URL verification proves preservation of all selected tags, their order, and reset to contract defaults. |
| `REQ-3704` | A browser test proves that the experimental section is separate and consent is not persisted. |
| `REQ-3705` | The owner/outsider matrix proves the public manage link and private preview redaction. |
| `REQ-3706`–`REQ-3707` | Tests compare the copied command with the canonical source and verify empty-state links. |
| `REQ-3708` | A mobile browser/a11y test reaches every signed-in route through navigation; `mobile-public-smoke.spec.ts` verifies keyboard/focus behavior for mobile navigation at 360 and 430 px in `ru` and `en`. |
