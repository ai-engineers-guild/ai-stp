---
description: "The desktop application is a Tauri shell that consumes the CLI machine contract and the /v1 catalog API; the CLI remains the sole authority for selection, installation, and recovery."
last_verified: "2026-10-01"
---

# ADR-0222: Desktop application is a contract consumer, not a second engine

Status: proposed.

## Context

The product needs a desktop application on macOS, Linux, and Windows that
lets a signed-in user browse the catalog, manage harness installations, and
operate the existing setup systems without consuming model tokens. The
invariant from `AGENTS.md` applies unchanged: the CLI owns selection,
assembly, installation, and native machine mutation; the web — and now the
desktop — owns account and catalog surfaces.

Reference implementation audited: HarnessKit (`hk-core` + Tauri + Axum,
v1.11.0). Its useful patterns (UI-agnostic core, capability-derived gating,
scope model, post-install verification, kit sync records) map onto surfaces
ai-stp already owns in the CLI; its weak patterns (unverified installers,
URL-carried tokens, permissive CORS, heuristic single-score trust,
client-side authority) are rejected.

## Options

- **Electron + Next.js reuse.** Reuses the running web app most literally,
  but duplicates a full Chromium + Node runtime per install, weakens the
  process/capability boundary, and the RSC-heavy pages do not port anyway
  (audit: ~75 route files are server-bound).
- **Flutter/Wails/Neutralino.** Each discards either the React design
  system or ecosystem maturity, and adds a language (Dart/Go) the repo
  does not otherwise need.
- **Tauri 2 + Rust shell + React/Vite frontend.** Small artifacts, a strict
  capability/CSP model, first-party plugins for updater, single instance,
  window state, and native HTTP; the frontend ports from `apps/web`'s
  design system (DTCG tokens, atoms, catalog organisms) through the shim
  boundary Storybook already proves.
- **A new Rust/TS domain core in the app** (HarnessKit's `hk-core` shape).
  Rejected outright for ai-stp: selection, plan digests, provider
  invocation, journal, and recovery already exist and are tested in
  `apps/cli`; duplicating them creates two authorities.

## Decision

1. The desktop app lives at `apps/desktop`: a Tauri 2 shell (Rust) plus a
   React/Vite single-page UI built from `apps/web`'s design system via the
   existing shim boundary.
2. **The CLI is the only engine.** The app invokes `ai-stp … --json`,
   parses exactly one envelope per call, validates `schema_version`, and
   renders `data`, `warnings`, `next_actions`, and `continuations`. It
   never writes harness files, never touches `registry.sqlite`, never
   invokes providers, and never infers command semantics from prose.
   Command argv is constructed from `help --agent --json` descriptors;
   everyday flows run through `task` intents.
3. **The app holds no credentials.** Sign-in drives
   `ai-stp auth login --provider P --json` → the UI renders `user_code` and
   opens `verification_uri_complete` in the system browser →
   `auth complete [--wait] --json`. Tokens, the Ed25519 device key, and the
   pending device code stay inside the CLI's ADR-0058 credential store.
   The OAuth `session_token` JSON callback path is a dead end (no refresh,
   no device binding) and is not used.
4. **HTTP reads use a native stack.** The API sets no CORS headers, so
   catalog and account reads run over Rust HTTP (not WebView `fetch`) with
   `Authorization: Bearer` obtained via CLI state, `X-AI-STP-Schema-Version: 1`,
   no redirect-following with credentials, and `Retry-After` honored.
   Only operations present in `schemas/v1/openapi.json` are called.
5. **Mutation UX mirrors the operation contract**: plan → effects review →
   approve bound to the exact `plan_digest` → apply → poll status →
   `verified`. `partial` is a recovery surface; `stale` triggers re-plan;
   plan TTL (900 s) is surfaced. Mutating calls serialize per target;
   `actor="external"` continuations mean poll-only.
6. **Trust is rendered as axes, never one score**: trust lane,
   `author_verified`, `component_verified`, check evidence, and provider
   trust/`v3_local_phase` are shown separately. Search results keep the
   contractual three-lane partition
   (`authoritative` / `local_owner_or_pinned` / `experimental`).
7. Release artifacts ship per-OS under the `desktop-v*` tag namespace (`v*`
   is the CLI's), with SHA256SUMS; bundles are unsigned — code signing and
   notarization are deferred until distribution requires them, so macOS
   Gatekeeper and Windows SmartScreen warnings are documented behavior. The
   embedded sidecar is named `ai-stp-desktop-cli` (never `ai-stp`), so
   Linux packages cannot collide with a standalone `ai-stp-cli` install at
   `/usr/bin/ai-stp`. Bundles are not promised byte-reproducible.
8. v1 scope: sign-in, catalog browse, environment/provider diagnostics,
   setup select → plan → approve → apply, status/drift, backups/rollback,
   devices, settings. Out of v1: corporate surfaces, publishing, a
   persistent local daemon, and any feature that calls a model API.

## Consequences

- `apps/desktop` joins the workspace; its Rust code and Vite UI add `cargo`
  and `bun` toolchains to developer setup for that tree only.
- The app depends on a resolvable `ai-stp` executable. Runtime distribution
  is resolved: release bundles embed the CLI as a PyInstaller-frozen sidecar
  (`bundle.externalBin`, `scripts/build-cli-sidecar.sh`), so no separate
  install is required; a configured path or PATH remains the development
  fallback. Every spawn runs under a filtered environment: `CliRunner`
  clears the inherited env and re-adds an explicit passthrough set
  (session, temp, profile, proxy, CA-bundle, and `AI_STP_*` variables),
  synthesizing a per-app temp dir when the parent supplies none. On
  Windows the temp/profile entries are load-bearing — the frozen
  bootloader resolves its `_MEI` extraction dir from them and dies with
  "Could not create temporary directory!" when they are stripped.
- Envelope `schema_version` mismatches fail closed with an update prompt;
  `registry_digest` invalidates the app's cached command descriptors.
- The provider co-owned roots (`~/.agents/skills`, `~/.claude/skills`) are
  surfaced in the UI when an operation touches them, because removal in one
  provider changes what other products read.
- Product scope documentation must be updated: the app is not a persistent
  daemon, but it does add auto-update machinery and a graphical setup
  editor, which `docs/product/scope.md` previously excluded.
- Tests: envelope parsing against the fixture corpus and mock transport in
  `packages/contracts`, continuation rendering rules, and an integration
  test driving `task start --intent inspect` end-to-end.

## Revisit conditions

- The bundled-CLI sidecar proves not viable in the field (size, signing,
  AV, or cold-start) — then distribution falls back to "require installed
  CLI" and the app gains a first-run bootstrapper flow.
- A second credential holder is ever required (e.g., the app acquiring
  without the CLI present) — then `device_type` gains `desktop` and the
  credential-storage decision in ADR-0058 is extended, not bypassed.
- Provider protocol v4 or envelope `schema_version: 2` ships — the app
  contract gate must tolerate-then-emit like every other consumer.
