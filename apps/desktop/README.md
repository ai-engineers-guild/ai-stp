# ai-stp desktop

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
  calls on `spawn_blocking`; capabilities are restricted to invoke/dialog/
  opener/process/window-state; strict CSP. IPC tiers: `cli_run_read`
  (mutability=`read` only), `cli_plan` (`plan` only),
  `cli_apply_confirmed` (`apply` + explicit UI confirmation), plus typed
  commands for auth, catalog, tasks.
- `src/` — React + Vite + Tailwind v4 UI, `HashRouter` + Zustand. Single
  `transport.ts` choke point; replies are typed `CmdResult`. Pages:
  Overview (CLI health/doctor/device), Account (device-code sign-in),
  Catalog (registry search/detail via CLI), Tasks (intents + status
  polling), Install (plan → digest review → apply), Targets
  (status/backups/diff/recover), Commands (live machine-help browser),
  Settings (scope selector: All is read-only aggregation).

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

Run the dev app (needs a display): `bunx tauri dev` from `apps/desktop`.

## Contract rules encoded here

- argv is built only from `help --agent --json` descriptors — undeclared
  parameters are refused before spawn;
- exactly one JSON object on stdout; unknown `schema_version` majors fail
  closed with an update prompt;
- errors are routed by `error.code` + `handling`, never message text;
- `actor="external"` continuations mean poll, not re-run;
- unknown `actor` values degrade to `human` — the app never auto-runs an
  argv it was not explicitly handed.

## Not yet done

- Per-target mutation serialization and cross-window coordination.
- CLI distribution: currently resolves a bundled `ai-stp` sidecar next to
  the executable, then PATH — no pinned runtime is shipped yet (D1).
- macOS/Windows packaging is configured but untested on those hosts.
- Recovery write flows (`install transaction recover`, `update recover`)
  are read-visible but have no dedicated apply UX yet.
