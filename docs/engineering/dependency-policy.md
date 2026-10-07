---
description: "Rules of Python, Node, external tools, and provider dependencies."
last_verified: "2026-10-07"
---

# Dependency Policy

A new dependency requires a specific capability gap, a primary source and release owner, a fixed version and lock, license and security checks, platform support, a timeout and failure model, a test, an update owner, and a plan for removal or replacement.

The external LSP, scanner, or tool is installed in an isolated set of tools and runs by exact path. Package installation scripts are disabled if their necessity is not proven.

A Git source is pinned to a specific commit. A dependency from the package registry has an exact version and integrity check. Arbitrary URLs are prohibited.

## CI tool bootstrap

The repository's Bun and uv bootstrap scripts download the exact release
archive and its published checksums before installing the binary. They retry
idempotent downloads after transport failures, with bounded connection,
transfer and total retry time. A checksum or installed-version mismatch still
fails the installation. Retry behavior follows the
[curl retry contract](https://curl.se/docs/manpage.html#--retry-all-errors).

## Installed CLI verification runtime

`apps/cli` owns the pinned `uv` runtime dependency and the isolated
`provider-verifier` dependency group. Their purpose, lifecycle, failure model,
supported qualification and removal path belong to
[ADR-0171](../adr/ADR-0171-installed-cli-owns-index-verification-runtime.md).
The verifier requirements are generated from `uv.lock` by `just back-gen`.

## Deferred migrations

A migration that is known and deliberately not made yet is recorded here with
the reason and the condition that ends the deferral, so the decision survives
the session that made it. Advisory exceptions are not listed: they live beside
the lockfile in `osv-scanner.toml`, where `ignoreUntil` makes the gate fail
again on its own.

Rechecked on October 7 against the primary release metadata: `yara-python`
4.5.4 still has no cp314 wheel; the three ESLint plugins below retain peers
through 9; `@hey-api/json-schema-ref-parser` 1.4.4 still pins `js-yaml` 4.2.0;
Dependabot's linked fix remains open. The httpx2 migration documentation still
specifies the OS trust store. None of these exit conditions has been met.

| Migration | Why it waits | Ends when |
|---|---|---|
| `httpx` 0.28.1 → `httpx2` (Pydantic-maintained successor; `httpx` is frozen, Starlette's `TestClient` and authlib warn) | The API is a rename, but TLS changes: `httpx2` verifies against the operating-system store through `truststore` instead of certifi's bundle. The published CLI and the frozen desktop sidecar would then trust whatever the host provides — on Linux, the CA paths compiled into the sidecar's bundled OpenSSL, which other distributions do not have. | A trust decision for the CLI and sidecar is made (an explicit context with a bundled fallback, or the OS store with evidence across Linux distributions, macOS and Windows) and the server and CLI move together. Recorded 2026-10-04. |
| Server images Python 3.12 → 3.14 (the interpreter `check.yml` gates) | `worker-safety` installs NVIDIA SkillSpector, whose `yara-python` publishes no cp314 wheel ([VirusTotal/yara-python#281](https://github.com/VirusTotal/yara-python/issues/281)); compiling it needs OpenSSL headers the pinned Debian snapshot cannot pair with the base. `pyright` holds the tree to the 3.12 API meanwhile. | `yara-python` ships cp314 wheels; then both Dockerfiles move to `python:3.14-slim`. Recorded 2026-10-04. |
| ESLint 9 → 10 for `apps/web` | `eslint-plugin-react` 7.37.5, `eslint-plugin-jsx-a11y` 6.10.2 and `eslint-plugin-import` 2.32.0 — the latest releases, which `eslint-config-next` 16 also depends on — declare `eslint` peers up to 9 only. | Those plugins publish ESLint 10 peer support; then `eslint` and the flat config move together. Recorded 2026-10-05. |
| `js-yaml` 4 → 5 in `apps/web` | The 4.x line is maintained (4.3.2, 2026-08-26). `overrides` holds the whole tree on it because `@hey-api/*` pins the vulnerable 4.2.0, and bun overrides cannot be scoped to one consumer: moving our three `load` calls to 5 would force 5 on every 4.x consumer or drop the patched pin. No runtime dependency needs 5 (`jsdom` 30 lists it only for development). | `@hey-api/*` and the other 4.x consumers accept a patched release without the override, or move to 5. Recorded 2026-10-05. |
| Dependabot `bun` updates for `apps/web`, `apps/desktop`, `docs_scripts` | The updater bundles bun 1.3 and cannot read `bun.lock` `lockfileVersion` 2 ([dependabot-core#16071](https://github.com/dependabot/dependabot-core/pull/16071)). OSV still scans every lockfile in the gate. | Upstream merges and ships the fix; the entries in `.github/dependabot.yml` resume by themselves. |

## Approved dependencies `apps/api` (issue #80, ADR-0041)

Each entry below is a sign-off for adding to `apps/api/pyproject.toml` and the root `uv.lock`. The exact version is fixed by the lock file during `uv lock` / `uv sync`.

### Pillow

`apps/api` owns Pillow for the SPEC-028 avatar decoder, orientation, bounded resize
and metadata removal. The exact version is locked in `uv.lock` (minimum 12.3.0).
Upstream is [python-pillow/Pillow](https://github.com/python-pillow/Pillow), with
HPND licensing and maintained Linux/macOS/Windows wheels. The decoder accepts
only JPEG/PNG/WebP after byte and pixel bounds; failures are typed validation
errors, and processing runs off the event loop. Image round-trip, metadata,
malformed-input and limit regressions cover this dependency. Platform maintainers
own advisory updates. Removing avatar normalization or replacing its tested
codec boundary removes Pillow from the API dependency graph; the CLI does not depend on it.

### authlib

| Field | Value |
|---|---|
| Capability gap | OAuth 2.0 / OIDC client for Google and GitHub: authorize redirect, token exchange, PKCE `S256`, binding `state` to the initiating session (`RFC 6749 §10.12`). Without a library, it would be necessary to manually implement CSRF/`state`/PKCE. |
| Source | PyPI `authlib`; main upstream — <https://github.com/authlib/authlib>. Release owner — Authlib maintainers. |
| Version | `>=1.6.6` (CSRF fix for state in cache); pin in lock to the current 1.7.x when adding. |
| License / security | BSD-3-Clause. Monitor GitHub/PyPI advisories; minimum 1.6.6 required. |
| Platforms | Pure Python; Python 3.10–3.14; Windows / Linux / macOS. |
| Timeout / failure | HTTP to provider via httpx with client timeout; token exchange failure → typed `AI_STP_AUTH_REQUIRED` / `AI_STP_DEPENDENCY_UNAVAILABLE` without secret leakage. |
| Test | OAuth callback/link/conflict/replay; state/PKCE negatives (`SPEC-002` REQ-202/203). |
| Updates Owner | platform / `apps/api`. |
| Removal Plan | Replace with another OAuth client only with the new ADR; delete the `slices/auth` OAuth adapter and dependency after migration. |

### cryptography

| Field | Value |
|---|---|
| Capability gap | Verification of the device's Ed25519 signature on the server (`Ed25519PublicKey.verify`), including authorship confirmation of the publication. Custom implementation of cryptographic primitives is prohibited. |
| Source | PyPI `cryptography`; upstream <https://github.com/pyca/cryptography>. Release owner — Python Cryptographic Authority. |
| Version | The current stable (50.x) is fixed in the lock. |
| License / security | Apache-2.0 OR BSD-3-Clause. Critical advisories are closed by an out-of-turn bump. |
| Platforms | Wheels for win/linux/macos x86_64 and arm64; Python 3.10+. |
| Timeout / failure | Local verify-only operation; invalid signature → `AI_STP_VALIDATION_ERROR` / registration refusal without exception with the key in the log. |
| Test | Device registration: valid/invalid signature, idempotency, attach-to-other denied (`SPEC-002` REQ-204). Bind attestation: a real signature is accepted, while `"s" * 16` and a foreign key are rejected (`SPEC-026` REQ-2605). |
| Updates Owner | platform / `apps/api`. |
| Removal plan | Only together with changing the device key scheme (parallel reading of old/new format according to SPEC-002); otherwise the dependency remains. |

### itsdangerous

| Field | Value |
|---|---|
| Capability gap | (1) Cookie signature `SessionMiddleware` of Starlette for transient OAuth state; (2) stateless signed nonce challenge of the device with TTL. Without it, Starlette's SessionMiddleware still requires a package, and the challenge would need a table and cleanup. |
| Source | PyPI `itsdangerous`; upstream <https://github.com/pallets/itsdangerous> (Pallets). |
| Version | 2.2.x is fixed in the lock. |
| License / security | BSD (OSI Approved). |
| Platforms | Pure Python; all target OS MVP. |
| Timeout / failure | Expired or forged nonce → registration denied; no side-channel on secret content. |
| Test | Challenge freshness, replay of stale nonce, device register path. |
| Update Owner | platform / `apps/api`. |
| Deletion plan | When abandoning SessionMiddleware and stateless challenge — a new ADR and removal of direct import; the transitive need for Starlette is considered separately. |

## Approved dependencies `apps/web` (issue #82/#83, ADR-0043)

`apps/web` — the first Node application of the repository and a separate Node workspace with its own
`package.json` and `bun.lock`, isolated from the root `uv.lock`. Package manager —
`bun`; the exact version of each package is fixed in `bun.lock` when added. Source —
npm registry with lock integrity check; arbitrary URL and Git source without exact
commits are prohibited (general rule above). Each line below is a sign-off for addition to
`apps/web/package.json` and `bun.lock` according to `ADR-0043`. The owner of updates for all lines is
platform / `apps/web`; the plan to remove any library is only with a new ADR with replacement,
without local editing.

### Runtime

| Package | Capability gap | Version / lock | License |
|---|---|---|---|
| `next` | App Router, RSC, Server Actions, server boundary and routing according to `ADR-0043`; frontend is attached in `tech-stack.md`. | Current stable major; pinned in `bun.lock`. | MIT |
| `react`, `react-dom` | Runtime UI required by Next.js. | Compatible with the chosen Next.js; pin in lock. | MIT |
| `next-intl` | Bilingual `ru`/`en` from the first route for App Router/RSC according to `ADR-0035` (`REQ-2203`, `REQ-2311`); without it, we would have had to manually handle localized routing and server translations. | Current stable; pin in lock. | MIT |
| `@hey-api/openapi-ts` (+ `@hey-api/client-fetch`) | Generation of types and typed client from `schemas/v1/openapi.json` (`REQ-2211`); prohibits a second DTO set alongside `#71`. | Verified in `jira_timesheet`; pin in lock. | MIT |
| `zustand` | Client-side store with thin slices according to `ADR-0043` (replacement of the global query cache); server truth is not duplicated on the client. | Current stable; pinned in lock. | MIT |
| `tailwindcss` (4.x) | Styles and tokenized theme on CSS variables according to `ADR-0043` (`REQ-2214`); compatible with standard `shadcn/ui`. | 4.x; pin in lock. | MIT |
| `class-variance-authority`, `clsx`, `tailwind-merge` | Utilities for variants and class merging for `shadcn/ui`. | Current stable; pin in lock. | MIT |
| `shadcn` (CLI/registry) + `radix-ui` primitives | Standard available components according to `ADR-0043`, organized by atomic design; component code is versioned in `apps/web`, and not pulled as a runtime dependency. Additional animation registries are not added. | Current stable; pin in lock. | MIT |
| `react-hook-form`, `@hookform/resolvers`, `zod` | Forms, validation of profile fields, environment variables, and external data at the boundary (`REQ-2201`, `REQ-2303`). | Current stable; pin in lock. | MIT |
| `js-yaml`, `@types/js-yaml` | Bounded parsing of repository-owned `features.yaml` and Markdown frontmatter according to `SPEC-038`; JSON schema disables implicit timestamps, Zod remains the ultimate boundary. | `js-yaml` 4.3.2, types 4.0.9; exact pin in manifest, lock and `overrides`. | MIT |
| `lucide-react`, `sonner` | Icons and safe feedback notifications (`REQ-2309`). | Current stable; pin in lock. | ISC / MIT |

Timeout / failure for runtime set: network calls go through a spawned client with
with a limited timeout; an unavailable API gives an observable error state
(`REQ-2205`), and not an empty or partial page; secrets and meanings of tokens in
client code, browser logs, and visible errors do not get captured (`ADR-0041`, `ADR-0043`).

### Dev and tests

| Package | Capability gap | Version / lock | License |
|---|---|---|---|
| `typescript` (7.x) | Main typecheck gate `apps/web` with the native compiler in strict mode according to `ADR-0043`. | 7.x; pinned in lock. | Apache-2.0 |
| `typescript` (6.x, side-by-side) + `typescript-eslint` | Type-aware lint (complete ban on `any`, ban on unsafe structural access): `typescript-eslint` does not work on TS7 until a stable API, so TS6 is installed alongside only for linting and removed upon the release of TS7.1 (`ADR-0043`). | TS6 `>=6.0 <6.1`; pin in lock. | Apache-2.0 / MIT |
| `eslint` (flat config) + `eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y`, `eslint-plugin-import` | Lint as a gate: rules for React/hooks, accessibility, import boundaries of atomic layers, and prohibition of god objects (`coding-rules.md`, `REQ-2213`). | Current stable; pin in lock. | MIT |
| `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom` | Unit and component tests of states, themes, and accessibility (`REQ-2202`, `REQ-2213`, `REQ-2214`). | Current stable; pinned in lock. | MIT |
| `@playwright/test` | Browser smoke `landing → search → detail` and login/review flows (`REQ-2213`, `REQ-2311`). | Current stable; pin in lock. | Apache-2.0 |
| `msw` | Mock-first development and tests against fixtures `#71` until ready `#80`/`#81`. | Removed: the in-process `mock-transport` fixture corpus replaced MSW; no consumer remained. | MIT |
| `prettier` | Frontend code formatting. | Current stable; pin in lock. | MIT |
| `storybook` + `@storybook/react-vite` + `@storybook/addon-essentials` + `@storybook/addon-a11y` + `@storybook/addon-themes` + `vite` + `@vitejs/plugin-react` + `@tailwindcss/vite` | UI kit / design-token Storybook for foundations and atomic components; dev-only, not runtime. Allows changing theme (tokens) without mixing with product routes. | Storybook 8.x; pin in `bun.lock`. | MIT |

Platforms of the entire set: Node LTS on Windows / Linux / macOS via `bun`; test
`run_conformance`-analogue on the web side — a contract test for type origin from
`schemas/v1/openapi.json`. The test of each library is covered by the acceptance criteria `SPEC-022`
and `SPEC-023`.
