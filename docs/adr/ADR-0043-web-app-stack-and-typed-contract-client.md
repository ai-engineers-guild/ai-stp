---
description: "apps/web uses Next.js App Router, TypeScript 7 with side-by-side TS6 linting, Tailwind 4 tokens, shadcn/ui under atomic design, Zustand, and the generated #71 client."
last_verified: "2026-08-06"
---

# ADR-0043: apps/web Stack and Typed Contract Client

Status: accepted.

## Context

`#82` and `#83` first materialize `apps/web`, the repository's first Node application
where previously only Python existed. `docs/engineering/tech-stack.md` names Next.js
as the frontend, and `SPEC-010` `REQ-1008` lists its surface, but the concrete stack
is not established anywhere: the Next.js dialect, language version, styling and theme
layer, bilingual library, component set and organization, method for deriving types
from the contract, data layer and client store, linter and typecheck, and package
manager and its lockfile. Without this decision, `#82` and `#83` would diverge into
incompatible shell implementations, and the first dependency addition would violate
`docs/engineering/dependency-policy.md`, which requires sign-off before a package
enters the lockfile.

The requirements of both issues narrow the choice more than they appear to. `#82`
requires generating or validating a typed client from `#71` and prohibits maintaining
a parallel hand-written DTO set: the contract is frozen in `schemas/v1/openapi.json`
(`#71`), so the web must generate types from it rather than describe them again.
`ADR-0035` requires Russian and English locales from the first route. `ADR-0018`,
`SPEC-010` `REQ-1011`, and `REQ-1012` prohibit a second implementation of business
logic in the web: the client calls the same API instead of making authorization
decisions itself. `ADR-0041` already selected the web transport (`HttpOnly; Secure;
SameSite=Lax` cookie, double-submit CSRF, and no long-lived provider tokens in the
browser). One stack must support both the `#82` shell and the `#83` authenticated
surface, so the decision is made once here.

TypeScript 7 creates a separate tension: its native compiler reached GA in 2026 and
typechecks roughly an order of magnitude faster, but it does not yet have a stable
programmatic API, so `typescript-eslint` and similar tools do not work with it and
declare a supported range below 7.0. The user's requirements for "TypeScript 7" and
"a relevant linter with a complete ban on `any`" can both be met only by explicitly
installing TS6 side by side for linting until TS7.1 provides a stable API.

The OAuth and session mechanism belongs to `ADR-0041`; the anonymous catalog read
model to `ADR-0042`; languages to `ADR-0035`; interface ownership to `ADR-0018`; and
frontend code conventions to `docs/engineering/coding-rules.md`. This record owns
only the frontend stack selection and the method of deriving types from the contract.

## Options

Next.js dialect:

1. App Router (React Server Components). Native server-side fetching for anonymous
   `#82` reads, server-side session reads for `#83`, and a built-in server/client
   boundary as a barrier against leaking private data into the client bundle. The
   cost is a newer model and care with "use client".
2. Pages Router. Simpler and older, but client-side fetching by default fits less well
   with the requirement not to embed hidden data in HTML and the bundle, and with
   server-side session reads.

Language version and linting:

1. TypeScript 7 for the primary typecheck plus side-by-side TS6 only for
   `typescript-eslint`. Provides fast strict typechecking with the native compiler
   while retaining type-aware lint rules (a complete ban on `any` and unsafe
   structural access) until TS7.1. The cost is two compiler versions in
   devDependencies during the transition.
2. TypeScript 6 only. Compatible with all tooling, but contradicts the explicit
   TypeScript 7 requirement.
3. TypeScript 7 only. Fastest, but deprives the project of type-aware linting and thus
   of the complete ban on `any` and lint enforcement against duck typing.

Styles and theme:

1. Tailwind CSS 4 with a tokenized CSS-variable theme: light and dark themes,
   semantic color tokens, and no hardcoded colors. Compatible with standard
   `shadcn/ui`.
2. CSS modules or runtime CSS-in-JS. More freedom, but less aligned with `shadcn/ui`
   and no unified tokenized theme out of the box.

Component set and organization:

1. Standard `shadcn/ui` (Radix primitives, Tailwind) without extensions, organized
   into `atoms`, `molecules`, `organisms`, and `layouts` layers under `atomic design`.
   Component code is versioned and edited in `apps/web`, rather than pulled as an
   opaque dependency.
2. `shadcn/ui` plus additional animation registries. Populates the landing page
   faster, but adds a dependency and visual layer not required by this slice.
3. A heavy UI framework (MUI/Chakra). Quick start, but a foreign theme, a larger
   bundle, and less control over accessibility and markup.

Contract client:

1. `@hey-api/openapi-ts` generates types and a fetch client from
   `schemas/v1/openapi.json`. The client is a generated artifact, is not edited by
   hand, and is rebuilt by a script. Directly satisfies `#82`'s prohibition on a
   competing hand-written DTO set.
2. Hand-written types and `fetch`. Fast at small scale, but creates a second source of
   truth alongside `#71` and diverges from the contract at the first change.

Data layer and client store:

1. RSC and Next Server Actions for server data and mutations (`revalidateTag`/
   `revalidatePath`), Zustand for client state, and `react-hook-form` + `zod` for forms
   and environment validation. Fewer dependencies, with no duplication of server
   truth on the client.
2. A client query-cache library (react-query and similar). A rich client cache, but
   an extra dependency and a temptation to keep server truth on the client contrary
   to the App Router model; not required by this slice.

Package manager and lockfile:

1. `bun` with `bun.lock`, with `apps/web` as a separate Node workspace isolated from
   the root `uv.lock`. Fast, with one runtime and test runner.
2. `npm` with `package-lock.json`. Most familiar, but slower and without a single
   runtime.

## Decision

The accepted stack is **Next.js App Router**, **TypeScript 7 with side-by-side TS6
for linting**, **Tailwind 4 with a tokenized theme**, **standard shadcn/ui under
atomic design**, **next-intl**, **`@hey-api/openapi-ts`**, **RSC + Server Actions +
Zustand + react-hook-form/zod**, and **bun**.

Dialect and structure:

- Next.js App Router on React Server Components with strict TypeScript. Private data
  is read on the server and does not enter the client bundle; `"use client"` is added
  selectively and does not pull in server secrets.
- `apps/web` is an independent Node workspace with its own `package.json` and
  `bun.lock`; it is not mixed with the root `uv.lock` or Python dependencies.

Language and linting:

- The primary typecheck uses the TypeScript 7 native compiler in strict mode
  (`strict`, `noImplicitAny`, `noUncheckedIndexedAccess`,
  `exactOptionalPropertyTypes`); this is an `apps/web` gate.
- `typescript-eslint` runs on the side-by-side installed TS6 and provides type-aware
  rules: a complete ban on `any` (`no-explicit-any` plus the `no-unsafe-*` rules) and
  a ban on unsafe structural access. Side-by-side TS6 is removed when TS7.1 provides
  a stable linting API. Concrete rules and boundaries are in
  `docs/engineering/coding-rules.md`.

Styles and theme: Tailwind CSS 4 with a CSS-variable theme from launch, including
light and dark themes and semantic color tokens; hardcoded colors are prohibited.
All user-facing strings are localized from launch through `next-intl` (`ADR-0035`);
literal user-facing text in markup is prohibited.

Components: standard `shadcn/ui` over Radix and Tailwind primitives without
additional registries, organized into `atoms`, `molecules`, `organisms`, and
`layouts` layers under `atomic design`; pages are assembled through App Router
routes. Import boundaries between layers are enforced by linting. Component code is
versioned in `apps/web`.

Contract client: `@hey-api/openapi-ts` generates types and a typed fetch client from
`schemas/v1/openapi.json`. Generated code is a build artifact: it is marked as
generated, is not edited by hand, and is rebuilt by the `api:generate` script. No
hand-written DTO set is maintained alongside `#71`.

Data and store: anonymous `#82` reads are performed by server components through the
generated client; `#83` data and mutations use Next Server Actions with
`revalidateTag`/`revalidatePath` against server truth (after `revoke`, the view is
updated from the server response, not optimistically). Client state is held by
Zustand in thin slices by responsibility boundary; server truth is not duplicated on
the client. Forms and environment validation use `react-hook-form` + `zod`. No
authorization decision is made on the client: route protection reads the server
session, while the final rule remains with the API (`ADR-0018`, `REQ-1011`,
`REQ-1012`).

Type discipline (boundaries are in `coding-rules.md`): complete ban on `any`; duck
typing is prohibited—identifiers and tokens are expressed nominally (branded types),
external data is accepted only through generated types and `zod` schemas, and unsafe
structural casts are prohibited; god objects are prohibited—modules are bounded by
responsibility and size, a shared dumping-ground `utils` and one global store are
prohibited, and the store is divided into slices.

Transport and tokens are inherited unchanged from `ADR-0041`. The package manager is
`bun` with a pinned `bun.lock`; the approved `apps/web` dependency list is maintained
in `docs/engineering/dependency-policy.md`.

## Consequences

- The repository gains its first Node toolchain: `bun`, `bun.lock`, and a Node
  lockfile policy for `apps/web`. `docs/engineering/dependency-policy.md` gains an
  `apps/web` dependency sign-off section; `docs/engineering/tech-stack.md` expands
  the Frontend row; `docs/engineering/coding-rules.md` gains a frontend conventions
  section.
- There is a transition period with two TypeScript versions: TS7 as the typecheck
  gate and TS6 as the peer for `typescript-eslint`. Both are pinned in the lockfile;
  TS6 is removed when TS7.1 provides a stable API, under a separate record.
- `apps/web` gains its own gates: linting with type-aware rules, typechecking on TS7,
  unit and component tests, build, and `browser smoke`; they join the shared
  `just check` and CI chain through the same local and CI path.
- The tokenized theme and localization are verifiable: linting prohibits hardcoded
  colors and literal user-facing strings, and a test confirms light and dark themes
  and locale parity.
- The generated contract client is rebuilt, not edited: a contract test proves that
  the types originate from `schemas/v1/openapi.json`.
- Development is mock-first: MSW serves `#71` fixtures until `#80`/`#81` are ready.
- Security: the App Router server boundary and the prohibition on a second business-
  logic implementation keep private data out of HTML and the bundle; token transport
  follows `ADR-0041`.
- Required tests: client generation and contract conformance, locale parity, light
  and dark themes, accessibility, behavior when the API is unavailable, route
  protection, and absence of private data from the client.
- Rollback: the dialect, language version, client generator, store, and package
  manager are encapsulated; changing any of them requires a new ADR and a rebuild,
  not an in-place edit.

## Reconsideration Conditions

The decision will be reconsidered if TS7.1 provides a stable API and side-by-side TS6
is no longer needed (TS6 is then removed under a separate record); if the RSC/App
Router model requires rules absent from the CLI API (violating `REQ-1011`); if
`@hey-api/openapi-ts` cannot express the frozen `#71` contract; if `bun` proves
unstable in CI on the target platforms; or if a demonstrated need for a browser setup
editor arises beyond the boundary of `ADR-0018`.
