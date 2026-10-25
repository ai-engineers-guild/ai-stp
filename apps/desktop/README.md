# ai-stp desktop

A Tauri 2 application over the bundled, optimized Rust CLI. The CLI owns all
business operations, credentials, SQLite state and harness installation. The
webview receives public JSON envelopes; it never invokes providers or writes
harness files. Harness executables remain user/vendor managed.

## Use

- **Overview** shows engine health, local identity and platform capabilities.
- **Settings** explicitly initializes a workspace with the selected credential
  store. Existing Python state requires the migration plan and exact digest
  exposed through Commands; initialization never replaces it.
- **Catalog** searches separate authoritative/experimental lanes. A published
  setup version can prefill the installation form with its exact ID and digest.
- **Setups** creates components through CLI questions or starts installation
  from explicit coordinates and target directories. Advanced inputs can use an
  existing JSON file. Starting and answering can execute changes immediately;
  the UI requires authorization and the CLI validates the full request.
- **Activity** lists unfinished tasks and opens any retained task by ID.
  Recovery reads the current revision; an uncertain start retains its retry
  identity in memory across navigation. After restarting the app, inspect
  Activity before starting again.
- **Account** drives device login, expiration, session refresh and retained
  operation recovery. It offers only methods reported by the selected server
  and supported by the native engine; discovery failure requires an explicit
  retry. Credentials stay in the CLI's selected store.
- **Targets**, **Discovery** and **Commands** render the connected engine's
  command descriptors with read/plan/apply gates and explicit apply confirmation.
- **Diagnostics** offers an optional, bounded in-memory trace and an explicitly
  copied redacted report. No telemetry or automatic diagnostic upload.

The engine reports installation availability. Isolated setup execution is
currently Linux-only; authoring and catalog reads remain available on macOS and
Windows. The desktop does not bypass an unsupported operation.

## Code

- `core/`: envelope parsing, descriptor-driven argv, executable resolution,
  filtered environment and bounded process execution. Linux session bus access
  is preserved for the existing OS keyring. A timeout leaves effects unconfirmed.
- `src-tauri/`: asynchronous IPC wrappers, serialized mutations and temporary
  public plan/input files. Form input is an object bounded to 16 KiB and passed
  unchanged to CLI schema validation; files are private and removed after use.
- `src/transport.ts`: the single IPC boundary. `store.ts` shares engine state;
  `taskStart.ts` retains a logical start's retry identity. Pages render the
  native contract; common visual primitives live in `components/` and `index.css`.

The app uses the shared web theme roles, vendored IBM Plex fonts, light/dark
appearance, visible keyboard focus and reduced-motion preferences. Technical
responses remain available in expandable details.

## Develop and verify

Use the Rust version in `apps/cli/rust-toolchain.toml` and the repository's pinned
Bun version. Native build and bundle probes run through the Rust tool in
`apps/cli/xtask`; desktop builds do not need Python or uv. Tauri needs the
platform webview development packages.

```sh
just desktop-gen       # Format Rust
just desktop-check     # Frontend, both Rust crates, real optimized sidecar
just desktop-bundle-test # Probe an existing packaged CLI resource tree
```

From `apps/desktop`, `bun run tauri dev` starts the native app. `bun run dev`
starts the frontend only and cannot perform operations without Tauri IPC.
Tests isolate IPC responses; sidecar regressions execute the actual native CLI.

Release bundles require their own `cli/ai-stp-desktop-cli` resource. A missing
bundled engine fails closed. Development can use `AI_STP_CLI` or PATH when no
bundled resource is present; a missing configured executable also fails closed.
The compile-time stub never overwrites a real sidecar.

## Release

Tag the verified commit `desktop-vX.Y.Z`, matching all desktop manifest versions,
then dispatch `.github/workflows/desktop-release.yml` on that tag. The workflow
checks and packages Linux, macOS and Windows builds and publishes `SHA256SUMS`.
Bundles are currently unsigned; no signing credentials are configured.
