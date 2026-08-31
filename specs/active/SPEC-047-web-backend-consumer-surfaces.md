---
description: "SPEC-047: Web/backend consumer surfaces for canonical CLI contracts and catalog delivery."
last_verified: "2026-08-15"
---

# SPEC-047: Web/backend consumer surfaces

## Purpose

Deliver the consumer-facing views of canonical CLI copy and `deep links` to the
shared product. Periodic GitHub archive evidence and account blast radius on
server/Web have been superseded by `SPEC-049` and `ADR-0096`. None of these
projections changes `immutable passport`, `lifecycle`, `eligibility`, or
`target`.

## Scope

Includes the delivery layer for issues #241, #307, #309, #344, and #347:

- generated and verified web projection of CLI copy templates;
- an actually executable `catalog coverage gate`;
- web consumer of `deep_link_v1`;
- server-owned cache and public projection for `GitHub archive evidence`
  (delivery removed: `SPEC-049`);
- `versioned authenticated API/web projection` for blast-radius reports
  (delivery removed: `SPEC-049`). The Account impact API may remain read-only,
  but Web does not display an installed baseline derived by the server.

Does not include:

- changing the `deep_link_v1` grammar from `SPEC-030`;
- changing local CLI behavior from `SPEC-043` and `SPEC-044`;
- automatic changes to `lifecycle`, `blocked/deprecated state`, or installation;
- GitHub credentials, private repository polling, or an external tokenizer;
- redesigning the web brand or creating a new visual language;
- browser authoring of passports, setup selection, or install flow.

The normative owners of existing meanings remain unchanged:

- `SPEC-030` and `ADR-0064` own `deep-link grammar` and `target semantics`;
- `SPEC-043` owns the estimator, capability delta, and `blast-radius semantics`;
- `SPEC-044` and `ADR-0082` own `GitHub observation semantics`;
- `SPEC-034` and `SPEC-037` own `catalog UX`, `copy actions`, localization, and
  `responsive interaction`.

This specification owns only the server/web delivery of these meanings and the
integrated `completion gate`.

## Terms

- **Consumer projection (`consumer projection`)** — a read-only representation
  of an already accepted contract on another surface, without new domain
  interpretation.
- **Public archive summary (`public archive summary`)** — a restricted web/API
  projection of the latest server-owned GitHub observation, without the raw
  response or credentials.
- **Account impact report (`account impact report`)** — a server-scoped version
  of the report, restricted to the current account and its authorized synced
  entities.
- **Canonical copy source (`canonical copy source`)** — a single
  machine-readable source for CLI copy templates, generated web constants, and
  contract tests.
- **Scoped gate (`scoped gate`)** — a separate verifiable quality gate with a
  fixed include scope, required by `just web-check`.

## Requirements

- `REQ-4701`: Web CLI copy templates use the canonical contract source. No
  hand-written copy of command grammar, distribution name, placeholders, or
  provider names remains in `apps/web`. The generated projection or mechanical
  drift check must fail the build when it does not match `packages/contracts`.

- `REQ-4702`: `just web-test` runs the scoped catalog coverage config together
  with regular web coverage. The gate has a fixed set of included production
  files from `vitest.catalog.config.ts`, requires at least 95% statements,
  branches, functions, and lines, and returns a nonzero exit code if any
  threshold is violated. Removing a file, lowering a threshold, or expanding
  exclusions does not constitute a fix.

- `REQ-4703`: The Web deep-link consumer uses the same packaged positive and
  negative corpus as contracts/CLI. The parser remains pure: it performs no
  catalog lookup, does not confirm that the target exists, and does not turn the
  URL into an enumeration source. It accepts only `deep_link_v1` routes and
  returns a normalized target, `cli_argv`, and a safe human projection.

- `REQ-4704`: Component, setup, exact-version, and publisher web surfaces
  provide canonical `Copy URL` and `Copy CLI command` actions wherever the
  target is available to the current projection. The exact-version surface
  includes a `#report` anchor for report intent. A hidden/private/inaccessible
  target does not reveal its existence or create a copyable link across the
  authorization boundary.

- `REQ-4705`: Server/Web delivery of periodic GitHub archive observations has
  been superseded by `SPEC-049` `REQ-4902`…`REQ-4905`. Local CLI evidence
  remains owned by `SPEC-044`.

- `REQ-4706`: Periodic worker refresh of the catalog has been replaced by the
  on-demand metadata request from `SPEC-049`. Catalog list does not initiate an
  external GitHub call.

- `REQ-4707`: Public catalog no longer carries a `github_archive` summary.
  Stars and the conditional `Archived` badge belong to `SPEC-049`.

- `REQ-4708`: The absence of GitHub metadata does not hide the catalog object or
  create a false warning; see `SPEC-049` `REQ-4903`/`REQ-4904` for details.

- `REQ-4709`: Local v1 `SelectionImpactReport` and `BlastRadiusReport` preserve
  `local_snapshot` / `local_registry`. The account blast-radius server contract
  was removed by `SPEC-049` `REQ-4906`.

- `REQ-4710`: `GET /v1/selection/blast-radius` has been removed.
  `GET /v1/selection/impact` remains a read-only authenticated resource without
  a Web baseline projection.

- `REQ-4711`: The Impact API does not fabricate zero cost or expose private
  objects belonging to others. Web does not read installed/selected state
  (`SPEC-049` `REQ-4911`).

- `REQ-4712`: Web does not display account blast radius or present an action as
  auto-update/uninstall. Context budget and CLI copy belong to `SPEC-049`.

- `REQ-4713`: All new web states and labels have RU/EN parity and keyboard-first
  behavior. Every interactive control has `default`, `hover`, `focus`, `active`,
  `disabled`, `loading`, and `error` states; `loading` uses a skeleton, while
  `stale`, unavailable, private, and validation cases explain the next safe
  action. The layout preserves the current design system, semantic tokens,
  visible focus, reduced motion, and WCAG 2.2 AA.

- `REQ-4714`: Every new API field, endpoint, migration, worker job, and
  generated client has a source contract, negative tests, a public/private
  matrix, migration/recovery evidence, and traceability to one of
  #241/#307/#309/#344/#347. An issue cannot be closed based only on unit tests
  without the exact SHA and an observed `just web-check`/`just back-check`
  result.

## States and errors

### Canonical copy and deep links

- `ready` — the canonical source and generated web projection match;
- `copy_failed` — the clipboard operation failed, but the URL/command remains
  available as text;
- `invalid_reference` — the parser rejected the URL/argv without normalization;
- `inaccessible` — Web preserves non-enumeration behavior.

### GitHub archive

The periodic archive projection states have been removed. On-demand metadata:
`SPEC-049`.

### Selection impact

- `ready` — report complete for the declared authority boundary;
- `partial` — an individual measurement is unavailable and the reason is
  visible;
- `stale` — the source revision or evidence is outdated;
- `invalid_graph` — the exact graph was refused before a partial report;
- `forbidden/not_found` — existing authorization and non-enumeration semantics.

## Security and privacy

- The GitHub client in the worker does not accept credentials from a request,
  passport, or Web.
- The Public API does not return the raw GitHub payload, the distinction that a
  repository is private, session/device identifiers, or private artifact bytes.
- `account impact` requests first verify account ownership, then load private
  rows, and do not use client-hidden fields for authorization.
- UI badges do not turn an `external observation` into a `trust claim`. Copy
  actions do not place tokens, local paths, credentials, or session state in
  URL/argv.
- Audit records and logs store the operation identifier and a restricted error
  category, but not the response body, headers containing credentials, or byte
  content.

## Compatibility and migration

1. Contracts and generated artifacts are published first; old CLI/web clients
   continue to read existing v1 responses.
2. Nullable storage for archive observations and a worker handler are then
   added; the absence of rows means `unavailable`, not migration failure.
3. After the migration is applied, the API begins returning optional
   `github_archive`. Old clients ignore the new field under the existing
   additive policy.
4. Server impact v2 is enabled through a separate endpoint/response schema; v1
   local CLI output does not change.
5. Application rollback does not delete observation history. Migration rollback
   is performed only under the `SPEC-020` backup/downgrade procedure and must
   not mask an already published catalog object.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-4701` | Web tests render every copy template and pass it through the real CLI parser; generated drift check fails on deliberate divergence. |
| `REQ-4702` | `just web-test` runs both configs; catalog suite reaches all four 95% thresholds and a deliberate branch regression fails. |
| `REQ-4703` | Shared positive/negative corpus and pure parser tests cover canonical and hostile URLs. |
| `REQ-4704` | Component/a11y tests and public/private Playwright matrix cover URL, CLI copy, exact-version report anchor and non-enumeration. |
| `REQ-4705` | The oracle belongs to `SPEC-049`: periodic archive evidence is no longer delivered. |
| `REQ-4706` | The oracle belongs to `SPEC-049`: catalog list does not call GitHub. |
| `REQ-4707` | The oracle belongs to `SPEC-049`: public catalog does not carry an archive summary. |
| `REQ-4708` | The oracle belongs to `SPEC-049`: the absence of metadata does not hide the object. |
| `REQ-4709` | CLI v1 schemas remain; generated API does not contain account blast radius. |
| `REQ-4710` | Generated inventory does not contain `/selection/blast-radius`. |
| `REQ-4711` | Impact API preserves non-enumeration; Web does not read installed/selected state. |
| `REQ-4712` | Web panel does not display blast radius or destructive update/uninstall actions. |
| `REQ-4713` | RU/EN parity, keyboard/focus, loading/error states and desktop/narrow viewport browser smoke pass. |
| `REQ-4714` | `just docs-check`, `just back-check`, `just web-check`, generated diff review and issue evidence run on the feature SHA. |
