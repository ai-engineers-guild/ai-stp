---
description: "SPEC-030: Canonical bidirectional links between CLI and web."
last_verified: "2026-08-09"
---

# SPEC-030: Canonical bidirectional links between CLI and web

## Purpose

Give the agent and web one versioned form for navigating to a component, setup,
exact version, publisher, or report action without a network lookup, hidden
browser launch, or passing secrets in a URL or command line.

## Scope

Included are the public `deep_link_v1` grammar, the `ru` and `en` locales, a
canonical URL, structured CLI `argv`, reverse parsing, and a shared corpus.
Browser launching, short links, a redirect service, private capability URLs,
and the identifier of a closed report case are excluded.

## Terms

- `target` — a typed stable ID of a component, setup, or publisher account;
- `intent` — either `view` or `report`; a report always addresses an exact
  object version;
- `cli_argv` — an array of arguments without shell escaping, suitable for an
  agent;
- `canonical URL` — an absolute platform URL with an explicit locale and no
  session data.

## Requirements

- `REQ-3001`: `deep_link_v1` supports a component/setup object, its exact `X.Y`
  version, a publisher account, and the `report` intent for an exact
  component/setup version.
- `REQ-3002`: A URL always contains the `ru` or `en` locale; if the caller does
  not specify it, the canonical default locale `ru` from web routing is used.
- `REQ-3003`: Components and setups use the existing catalog routes, publishers
  use the existing public-profile route, and the `report` intent uses the exact
  version URL with the fixed `#report` fragment; no new server route is created.
- `REQ-3004`: A link is built only from the validated platform origin, kind,
  canonical stable ID, optional exact version, locale, and intent. Query,
  credentials, token, device ID, local path, and arbitrary fragment are
  impossible.
- `REQ-3005`: Each target returns a URL, normalized link, and `cli_argv`; the
  human-readable command is a deterministic projection of the same array, not a
  second source of truth.
- `REQ-3006`: The `target → URL → target` and
  `target → cli_argv → target` round trips preserve kind, stable ID, exact
  version, locale, and intent byte for byte.
- `REQ-3007`: Generation and parsing do not access the catalog/API or verify
  object existence. Availability and enumeration prevention remain at the
  existing web/API authorization boundary.
- `REQ-3008`: The CLI prints the link but does not open a browser automatically;
  the same command must work locally, over SSH, and in machine mode.
- `REQ-3009`: CLI, contracts, and web use one versioned positive and malicious
  corpus; any difference in URL, argv, or parsing is a contract error.
- `REQ-3010`: Unknown grammar version, locale, kind, or ID prefix, a
  non-canonical version, an extra path segment, query, credentials, or fragment
  produces a typed validation rejection without normalizing dangerous input.

## States and errors

The command either returns one complete `DeepLinkView` or a typed validation
error. A target's absence from the catalog is not a link-construction error and
does not turn a pure command into an object-enumeration source.

## Security and privacy

Neither the URL nor `cli_argv` contains auth/session state. Stable IDs and the
version pass closed validation before URL encoding. Parsing trusts only the
configured platform origin and canonical grammar; an external link is not
converted into a CLI command.

## Compatibility and migration

`deep_link_v1` is immutable. A new kind, locale, route form, or intent requires
a new grammar version and a period of compatible parsing. Web may preserve
redirects from the old grammar, but canonical output always uses one current
form.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-3001` | The golden corpus covers component/setup, exact versions, publisher, and report intent. |
| `REQ-3002` | Verification of the default and both explicit locales fixes `ru` and `en` in the URL and `cli_argv`. |
| `REQ-3003` | Golden URLs use only existing object/version/publisher paths and `#report`. |
| `REQ-3004` | The negative corpus rejects credentials, query, extra secret-like fields, an invalid ID prefix, and an arbitrary fragment. |
| `REQ-3005` | The schema golden fixes the normalized target, URL, `cli_argv`, and derived command. |
| `REQ-3006` | Property and round-trip checks compare the target, URL, `cli_argv`, and parsing result. |
| `REQ-3007` | A generation check prohibits catalog/API lookup and accepts a syntactically valid unknown ID. |
| `REQ-3008` | A CLI check prohibits browser calls and works under an SSH model with the catalog disabled. |
| `REQ-3009` | A Python contract check reads the packaged corpus; the web owner consumes the same file without a copy. |
| `REQ-3010` | Boundary checks cover every closed enumeration and structural constraint. |
