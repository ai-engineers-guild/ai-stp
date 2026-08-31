---
description: "SPEC-022: Web shell, bilingual landing page and anonymous public catalog."
last_verified: "2026-08-17"
---

# SPEC-022: Web shell, landing page and anonymous catalog

## Purpose

`apps/web` provides the platform's anonymous web surface for the first time: a materialized
Next.js shell with bilingual routes, loading, error, and empty states, and
environment validation; a landing page with the exact installation command from a single
canonical source; public search and listing of components and setups with cursor
navigation; card and exact version of the object with publisher, harness, compatibility
and a verification summary; the first-party publisher's public profile required by the seed corpus.
All this works without an account and safely degrades when the API is unavailable.

Wire contract frozen `#71` in `schemas/v1/openapi.json` and models
`ai_stp_contracts`; this specification does not override it, but describes the behavior of the web
behind it and owns the `REQ-22xx` requirements. The stack, generated typed
client and bilingualism belong to `ADR-0043`; product languages ​​- `ADR-0035`; possession
interfaces and prohibition of second business logic - `ADR-0018`; anonymous reading model and
trust lines — `ADR-0042`, `ADR-0016`; server-side catalog behavior — `SPEC-021`;
public profile fields - `docs/contracts/public-profile.md`; HTTP rules, cursor and
errors - `docs/contracts/http-api.md`.

## Scope

Includes: materialization `apps/web` (Next.js App Router, Node lock policy of the repository,
checking the environment); route bases, layout, error and loading; Russian and
English locale from the first route without mixed language; landing page with the exact command
installations from `#77` and copy action; public search and listing of components and
setups with an opaque cursor; object card and exact version page with
publisher, harness, compatibility and check summary; public profile
first-party publisher; typed client derived from `#71`; available
keyboard, focus, error, empty, and loading states; fixed budgets
performance and availability.

Does not include: browser-based setup editor; recommendations and composition assembly; publication,
synchronization, rights, complaints and administration; authenticated pages
account and device (`#83`, `SPEC-023`); changing general wire diagrams and `schemas/**`
(owner — `#71`); server-side catalog behavior and seeding (`SPEC-021`); domain
semantics of accounts and devices (`SPEC-002`).

## Terms

- `Web shell` — materialized shell `apps/web`: routes, layout, boundaries
  error and loading, environment check and locale providers according to `ADR-0043`.
- `Install command` - the exact installation command from the only canonical
  source `#77`; The web copies it verbatim and does not assemble it from parts.
- `Public route` - route available without an account: landing, search, card, version,
  public profile.
- `Generated contract client` - types and client derived from `schemas/v1/openapi.json`
  generator `ADR-0043`; manual DTO dialing is not carried out next to it.
- `Card projection` - projection of `ComponentSummary`/`SetupSummary` from `SPEC-021`: fields
  object and `latest_*` from the passport of the latest proposed version.
- `Locale parity` is a property in which `ru` and `en` carry equivalent information
  and the same route behavior, not different volumes.

## Requirements

- `REQ-2201`: `apps/web` materializes as a Next.js App Router application
  `ADR-0043` with Node lock policy repository; missing or invalid variable
  environment is detected by a check at startup and gives an explicit failure, not a silent one
  default
- `REQ-2202`: The wrapper provides route bases, general layout and boundaries
  `error` and `loading`; each data read has observable load states,
  error, empty, and data states covered by tests.
- `REQ-2203`: Russian and English locales are available from the first route via `ADR-0035`;
  no user text is hardcoded in one language or mixes languages;
  both locales carry equivalent information and the same route behavior.
- `REQ-2204`: Landing page shows the exact installation command from the only
  canonical source `#77` with a copy action and prerequisites; the command is not
  assembled by the web from parts and does not diverge from the source; before the adoption of `#77`
  the source is considered unsecured and the landing page is not accepted.
- `REQ-2205`: Public routes are rendered without an account; when the web API is unavailable
  fails with a safely observable error state rather than empty or partially
  collected page and not inventing data.
- `REQ-2206`: Searching and listing components and setups uses an opaque cursor across
  `docs/contracts/http-api.md`: the client returns the cursor verbatim and does not parse it,
  the traversal does not repeat or skip the object, the page size does not exceed the contract size
  maximum; components and setups are separate resources, and a cursor for one resource
  type is not accepted for the other.
- `REQ-2207`: The card and the exact version page fill in the fields from the `#71` projections
  (`*Summary`/`*Detail`/`*VersionResponse`) and show the publisher, harness,
  compatibility and test summary; each field corresponds to a contract field, not
  calculated separately by the web; the web does not promise continuity of version numbers
  (`docs/contracts/http-api.md`).
- `REQ-2208`: Trust lines for `ADR-0016` are presented as in the contract: section
  `authoritative` only with both true axes `author_verified` and
  `component_verified`; section `experimental` is shown only when request-scoped
  consent and in a separate section, and not mixed together; verified author status is not presented as
  proof of content safety.
- `REQ-2209`: Hidden, private and draft data are not requested, not
  preloaded and not embedded in HTML or client bundle; the web does not bypass
  `AI_STP_NOT_FOUND` and does not display the existence of a non-public record either by the counter or
  response form.
- `REQ-2210`: Public profile of the first-party publisher shows only fields
  `docs/contracts/public-profile.md` (`display_name`, `bio`, `links` with HTTPS) and
  published account objects; empty profile shows only id
  account and its objects, not an empty card; device data is not included in the profile.
- `REQ-2211`: Web request and response types are derived from `schemas/v1/openapi.json`
  generator `ADR-0043`; there is no manual competing DTO dialing; contract test
  proves the origin of types from contract, and the divergence of prose and contract
  is decided in favor of the contract.
- `REQ-2212`: No web-specific catalog behavior diverges from the CLI and API:
  search, card and web version reflect the same fields and the same order as the general one
  flow (`REQ-1011`, `SPEC-021`); web does not implement duplicate catalog business logic.
- `REQ-2213`: Interactive elements are keyboard accessible, have visible focus and
  correct roles and signatures; error, empty and loading states are declared
  assistive technologies; fixed performance and availability budgets
  measured and verified.
- `REQ-2214`: The shell sets a tokenized theme from launch: the color is taken only from
  semantic theme tokens, light and dark themes are supported, and hardcoded
  the color value in the component is prohibited and rejected by the gate; custom strings
  are taken from localized directories, and not from markup literals (`ADR-0035`,
  `ADR-0043`, `docs/engineering/coding-rules.md`).

## States and errors

Reading public route succeeds with resource body observed
the state of emptiness in the absence of results, the state `AI_STP_NOT_FOUND` for
missing or non-public record (indistinguishable), typed invalid error
request with a tampered or foreign cursor and an unknown parameter or state
unavailable dependency when API is unavailable. Web shows secure message
errors and `X-Request-Id`, without revealing internal details and without embedding private
data. Silently discarded filter is disabled: unknown parameter gives an error, not
complete catalog (`docs/contracts/http-api.md`).

## Security and privacy

The anonymous route is the main discovery channel, so the web only represents
published public passport and permitted projections. Private, draft and
hidden entries are not requested and are not embedded in HTML, client bundle or
preload. The existence of a non-public record is not displayed via the web either by direct ID or
no cursor, no counter, no time-dependent response form. Object key
opaque and lacking authority; object bytes are issued in a separate verified step
servers (`SPEC-021`, `ADR-0042`). Secrets, tokens and environment values are not included in
client code, browser logs and fixtures.

## Compatibility and migration

The `#71` contract in this sprint is changed only additively and only by `#71`;
the discrepancy between the issue prose and the frozen contract is resolved in favor of the contract, and
the need for a new field (for example, card publisher) is formalized as an additive
application to `#71`, and not as a local rejection of the web. Derived client
reassembled upon additive change of contract; manual DTO dialing is not entered.
The installation command is taken from `#77` and changes only with it.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-2201` | The test confirms the start of `apps/web` and an obvious failure with a missing mandatory environment variable. |
| `REQ-2202` | Component and route tests cover loading, error, empty, and data states. |
| `REQ-2203` | The locale parity test confirms that `ru` and `en` have equivalent information and behavior and that there is no hardcoded mixed language. |
| `REQ-2204` | The test confirms the verbatim match of the installation command with the canonical source `#77` and the presence of the copy action and prerequisites. |
| `REQ-2205` | The API Unreachable test confirms a safe error condition without a blank or partial page. |
| `REQ-2206` | The test confirms the verbatim cursor return, the absence of duplicates and gaps during pagination, the page limit and the separation of components and setup resources. |
| `REQ-2207` | The contract-fixture test maps every card, detail, and version field to a contract field and confirms that the publisher, harness, compatibility, and verification summary are shown. |
| `REQ-2208` | The test confirms the presentation of `authoritative` only in both axes and the appearance of `experimental` as a separate section only with agreement. |
| `REQ-2209` | The HTML and bundle inspection test confirms the absence of hidden, private and draft data and the indistinguishability of `AI_STP_NOT_FOUND` from the missing entry. |
| `REQ-2210` | The golden test of a public profile confirms only allowed fields, the display of an empty profile with an identifier and objects, and the absence of device data. |
| `REQ-2211` | The contract test confirms the generation of types from `schemas/v1/openapi.json` and the absence of a manual competing DTO set. |
| `REQ-2212` | Contract verification confirms that the web fields and ordering match the shared catalog flow and that there is no duplicate business logic. |
| `REQ-2213` | Accessibility checks and committed performance budgets are performed and passed; browser smoke `landing → search → detail` passes; `mobile-public-smoke.spec.ts` passes at 360 and 430 px in `ru` and `en` without document-level overflow and with visible install/view CTA. |
| `REQ-2214` | The test confirms the light and dark themes and the origin of the color from the tokens; The gate rejects hardcoded color and literal user string. |

Browser scripts `apps/web/tests/e2e/` close the executable layer for `REQ-2203`
(`locale-parity.spec.ts`), `REQ-2205` (`catalog-error-states.spec.ts`),
`REQ-2206` (`catalog-pagination.spec.ts`) and `REQ-2213` (`a11y.spec.ts`,
`perf-budget.spec.ts`, `landing-catalog.spec.ts`, `mobile-public-smoke.spec.ts`).

`apps/web/tests/component/` component tests close the executable layer for
`REQ-2202` (`state-panel.test.tsx` - loading states, errors and emptiness together
with their announcement of assistive technologies; `catalog-results.test.tsx` - states
data and emptiness of both sections), `REQ-2207` (`object-card.test.tsx` - binding
fields of the card to the body of the contract fixtures) and `REQ-2208` (`object-card.test.tsx` -
`authoritative` only for both axes, axes are independent; `catalog-results.test.tsx` —
an unacknowledged object is not included in the markup without consent, rather than simply hidden).

Coverage remains incomplete consciously: `catalog-filters`, `device-list`,
`identity-list`, `profile-form` and `install-block` component tests are not yet available
have. The weight of client JS is measured from the `REQ-2213` budgets; `lcpMs`, `cls` and
`tbtMs` are recorded in `apps/web/src/lib/budgets.ts` as unmeasured and passed
are not considered.
