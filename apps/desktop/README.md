# ai-stp-desktop

Tauri 2 shell + React/Vite UI over the `ai-stp` CLI machine contract
(ADR-0222). The CLI is the only engine: this app spawns `ai-stp … --json`,
parses the single JSON envelope, and renders it. It never writes harness
files, never touches `registry.sqlite`, never invokes providers, and never
holds user credentials.

## Layout

- `core/` — pure-Rust, transport-free crate: envelope parsing
  (`schema_version` gate, `continuations`, `error.code`), command-registry
  argv construction from `help --agent --json` descriptors
  (`parameter_rules`, `choices`, `required`), CLI process runner
  (executable resolution bundled → configured → PATH, env pinning, bounded
  wait, timeout = effect unconfirmed).
- `src-tauri/` — thin Tauri shell: `#[tauri::command]` wrappers run core
  calls on `spawn_blocking`; capabilities are restricted to core invoke/
  window, `opener` URLs (HTTPS plus loopback HTTP for local providers),
  and `window-state`; plugins are single-instance, window-state, and
  opener; strict CSP. IPC tiers: `cli_run_read`
  (mutability=`read` only), `cli_plan` (`plan` only),
  `cli_apply_confirmed` (`apply` + explicit UI confirmation), plus typed
  commands for auth, catalog, tasks.
- `src/` — React + Vite + Tailwind v4 UI, `HashRouter` + Zustand. Single
  `transport.ts` choke point; replies are typed `CmdResult`. Pages:
  Overview (CLI health/doctor/device), Account (device-code sign-in),
  Catalog (registry search/detail via CLI), Tasks (intents + status
  polling), Install (task-engine journeys: questions → continuations →
  gated apply), Discovery (native component/harness discovery joined to
  the registry by stable_id), Targets (status/backups/diff/rollback
  preview + stopped transaction recovery), Commands (live machine-help browser),
  Debug (IPC trace, resolved engine, envelope inspector, diagnostic
  bundle), Settings (scope selector: All is read-only aggregation).

## Design system

Tokens and rules are mirrored from `apps/web` (`docs/product/DESIGN.md`,
`apps/web/src/theme/tokens.json`): IBM Plex Sans/Mono (vendored woff2,
unicode-range split), semantic HSL channels under `:root`/`.dark`,
component primitives (`.card`, `.btn-primary`, `.input`, `.chip`, …) in
`src/index.css`. Raw hex in components is prohibited; accent orange is
reserved for CTAs and active markers. Light/dark follows the OS with a
manual toggle in the sidebar.

## Debug mode

Every IPC call is recorded (command, args, latency, ok/error_code, full
envelope) in a bounded ring buffer — open the Debug page to inspect the
trace, expand any call's raw envelope, run a read-gated probe command, or
copy a redacted diagnostic bundle. `debug_info` reports which CLI binary
was resolved and from where. The sidebar badge counts failed calls.

## Build and test

```bash
# Rust core (no GUI deps required)
cd core && cargo test                      # unit tests
cd core && cargo test -- --ignored         # + real ai-stp on PATH

# Frontend
bun install && bun run build

# Tauri shell (needs OS webview dev packages; Debian/Ubuntu:
# libwebkit2gtk-4.1-dev libsoup-3.0-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev)
cd src-tauri && cargo check && cargo build
```

From the repository root, `just desktop-check` runs the same group CI
runs: frontend tsc/vitest/build, fmt+clippy+tests for both crates, and a
`desktop-regress` leg that freezes the real PyInstaller sidecar — that
freeze takes several minutes — and spawns it under the app's filtered
environment. `just desktop-gen` formats both crates. The `--stub` sidecar
these recipes install is a dev-only placeholder that answers
`version --json`; it is never written over a real build.

Run the dev app (needs a display): `bunx tauri dev` from `apps/desktop`.

## Contract rules encoded here

- argv is built only from `help --agent --json` descriptors — undeclared
  parameters are refused before spawn;
- exactly one JSON object on stdout; unknown `schema_version` majors fail
  closed with an update prompt;
- errors are routed by `error.code` (+ `retryable` and structured
  `details`/`next_actions` passthrough), never message text; shell-local
  failures use `DESKTOP_*` codes, never the CLI's `AI_STP_*` namespace;
- `actor="external"` continuations mean poll, not re-run;
- unknown `actor` values degrade to `human` — the app never auto-runs an
  argv it was not explicitly handed.

## Releases

`.github/workflows/desktop-release.yml` builds and publishes a GitHub
Release for all three OSes. Tag the release commit `desktop-vX.Y.Z` where
`X.Y.Z` equals `src-tauri/tauri.conf.json` → `version`, push the tag, then
dispatch the workflow with that version. The run refuses to proceed on any
other ref, verifies the tag/version match, runs the full check set per OS,
checksums every artifact (`SHA256SUMS`), and attaches bundles to the
release. Bundles are unsigned — signing/notarization is a separate track.

## Requirements

Release bundles carry the CLI inside: `scripts/build-cli-sidecar.sh`
builds the `ai-stp-cli` wheel, installs it into a fresh environment with the
hash-checked, locked closure of the dependencies it declares — what
`pip install ai-stp-cli` gets, nothing from the server or dev groups — and
freezes that with PyInstaller into
`src-tauri/sidecar/ai-stp-desktop-cli-<triple>`, and Tauri
`bundle.externalBin` installs that binary next to the app executable —
where the resolver's bundled-path tier finds it first, so no separate
install is required. The `ai-stp-desktop-cli` name is deliberate: a bare
`ai-stp` sidecar would land at `/usr/bin/ai-stp` in Linux packages and
collide with a separately installed CLI. For development, resolution
falls back to a configured path and then PATH
(`uv tool install ai-stp-cli`); a pinned path that is missing is an
error, not a silent fallback.

## Not yet done

- Signed/notarized bundles — needs signing certificates and notarization
  credentials; `SHA256SUMS` in each release covers integrity until then.
- Native Rust HTTP catalog reads against `/v1` (the CLI proxies catalog
  traffic today, which also covers private acquisitions on its own
  credentials — deliberate, not a gap).
- Per-target mutation parallelism — mutations serialize on one mutex
  because the CLI journal is global state; targeted parallelism would
  not make journal writes any safer.
