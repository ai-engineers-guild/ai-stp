---
description: "Versioned agent-first deep links between CLI and web without network lookup or implicit browser launch."
last_verified: "2026-08-09"
---

# ADR-0064: Canonical CLI/web deep links

Status: accepted.

## Context

CLI and web already refer to the same stable IDs and exact versions, but navigation between them has no shared contract. Simple string concatenation in each consumer would create differing plural routes, locales, quoting, and report URLs. The `open` command, in turn, is unsuitable as the primary agent contract: a browser is unavailable over SSH, and an implicit launch is a side effect in a command that should only orient the agent.

Routes for component/setup exact versions and publishers already exist in web. The report creation route belongs to future platform/web work and has not yet been frozen; CLI must not invent it on behalf of the platform owner.

## Decision

The `deep_link_v1` grammar and a pure CLI command are adopted. The command prints `DeepLinkView`: a normalized target, an absolute canonical URL, structured `cli_argv`, and its deterministic human projection. The browser is not opened automatically.

Component/setup objects and exact versions use the existing route hierarchy. Publisher uses the public profile route by `account_` stable ID. Report intent addresses an exact version and adds the only permitted fragment, `#report`. This allows the intent to be preserved until the UI action appears, without creating an API/server route or changing non-enumeration rules.

The default locale is `ru`, as in web routing. Both canonical locales are always explicitly present in the URL. The platform base is taken from the active configuration and passes the existing scheme/authority validation; the deep-link parser additionally requires an exact match with the configured origin and base path.

The grammar is implemented in the shared contracts package and accompanied by a single packaged JSON corpus. CLI uses the Python implementation; the web owner implements the route/parser and validates it against the same corpus. Generation performs no lookup: otherwise, the command would simultaneously become network-dependent, unsuitable for offline use, and an oracle for the existence of a private target.

## Considered Alternatives

1. Automatically open the browser. Rejected as a nondeterministic side effect that does not work consistently locally and over SSH.
2. Add a URL to the responses of every catalog command. Deferred: this duplicates the grammar across many models and does not cover publisher/report with a single action.
3. Create `/reports/new` from CLI. Rejected: the route and authorization belong to the platform/web owner and have not yet been frozen.
4. Use the query string for identity. Rejected: existing resource routes already express identity in the path, while a query is easier to accidentally extend with session data.

## Consequences

The agent receives an exact URL and safe `argv` without shell quoting and without network access. Web can display a copyable command without maintaining a second route dictionary. The presence of a link does not assert the existence or availability of the object; the final answer remains with web/API. Report intent requires an anchor named `report` on the exact-version surface when the platform/web slice is implemented.

## Reconsideration Conditions

The decision will be reconsidered when a third locale, a separate immutable report target, a short-link service, or an incompatible route hierarchy appears. Each such change receives a new grammar version rather than modifying `deep_link_v1` in place.
