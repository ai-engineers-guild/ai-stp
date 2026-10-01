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
  opener/process/window-state; strict CSP.
- `src/` — React + Vite + Tailwind v4 UI. Single `transport.ts` choke
  point; replies are typed `CmdResult`.

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
- mutating calls are serialized per target (wired in the shell layer).
