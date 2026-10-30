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
  Corporate checkout history is read from the native journal across saved views.
  Inspect the original plan and explicitly reconcile an unknown outcome through
  a current context for the same account/company. Switching views cannot retarget
  the original operation; unknown results retain their reservations.
  A completed adoption keeps its original receipt. When the exact server link
  has been unlinked, a separate native review can release only that local
  binding's reservation. It rechecks current rights, physical checkout and
  retained state, preserving files, tasks and harness configuration. Activity
  reads the distinct retirement receipt after restart; it never interprets an
  old adoption receipt as proof that a binding is still active.
  If the retained checkout name is absent, use the separate missing-checkout
  review in Activity. The CLI requires a positively unlinked original server
  result, current original-account company access and the same inspectable
  physical parent. A present/reappeared entry, dangling link or unavailable
  parent refuses. Confirming releases only this original local reservation;
  moved files remain untouched. Its distinct receipt survives restart and
  pathname reuse. The app never falls back to this action automatically.
  Engines exposing reviewed locations can save a full-identity anchor while
  the registered checkout exists. Close the app and other processes holding
  the checkout before manually moving that same directory. Reopen Activity,
  inspect the original adoption and review the existing destination. Applying
  the confirmed native plan updates only location metadata; the app does not
  move files. The CLI requires the original path to be absent, unchanged Git
  topology, matching physical identity, current company access and no conflicting
  work. Copies or a missing anchor require separate recovery. Recorded locations
  and their exact receipts remain readable after later moves and retirement;
  an old receipt does not establish the present directory. Unconfirmed replies
  retain the same plan and offer offline outcome lookup before an explicit retry.
  Recovery reads the current revision; an uncertain start retains its retry
  identity in memory across navigation. After restarting the app, inspect
  Activity before starting again.
- **Account** drives device login, expiration, session refresh and retained
  operation recovery. It offers only methods reported by the selected server
  and supported by the native engine; discovery failure requires an explicit
  retry. Credentials stay in the CLI's selected store.
- **Connections** creates and recovers independent native enrollments through
  reviewed plans, opens each account session separately and retains native offline,
  personal and corporate context observations. It exposes the exact registry
  format upgrade before application. View selection preserves existing operations
  and harness files; current organization access is an explicit online read.
  The existing local-owner session can be admitted as a context through the same
  reviewed flow, preserving its original key and credential journal.
  After native identity recovery, an older saved view can still read history.
  A new checkout review requires a current identity; its native refusal offers
  **Review current context** in Connections. Use the same existing sign-in and
  company for a fresh reviewed context, then select it explicitly. The app does
  not rewrite old views, transfer original intents or start another sign-in.
- The sidebar selects an existing personal or corporate context for new company
  reads. Selection is a local preference; retained tasks keep their original
  authority. The account shortcut opens the selected named connection.
- **Company** explicitly reads projects, teams, technologies, immutable mappings
  and the organization catalog. Assignment previews offer every harness reported
  by the engine and use an empty company-managed inventory. They do not apply
  installations or include personal setup files. Replies from an earlier context
  are discarded, including after switching away and back to the same context.
  Catalog and technology pages retain their search filters for explicit next-page
  reads; catalog versions and assignment digests are visible in the result cards.
  A project can open a native checkout review with an existing registered root
  and optional trusted Git executable. A successful preview exposes current
  corporate repository choices for a separate recheck. Editing inputs or switching
  contexts clears the observation. Engines exposing durable linking offer separate
  reviewed requests, confirmations and local binding adoption. Each exact plan
  needs explicit authorization. An unconfirmed reply retains its original intent
  for Activity rather than starting another request. Linking grants no harness
  installation authority.
- **Targets**, **Discovery** and **Commands** render the connected engine's
  command descriptors with read/plan/apply gates and explicit apply confirmation.
- **Diagnostics** offers an optional, bounded in-memory trace and an explicitly
  copied redacted report. No telemetry or automatic diagnostic upload.
  Context and corporate commands retain only transport outcome and timing in
  this shared trace; their arguments, replies and error prose are omitted.

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

Linux installed-package qualification also scans the real webview with the
axe-core artifact pinned by the existing web lock. It checks both themes,
retained personal profiles, keyboard skip-link activation and actual loading
indicators after an owned GTK reduced-motion preference and app restart.
Reports retain rule IDs, impacts, counts and bounded contrast operands;
incomplete axe checks still need review. Startup and CLI read timings are
observations, not an
assertion of a performance budget or complete screen-reader conformance.

Linux CI also installs its release Debian package and drives the installed app
through external WebKit WebDriver under Xvfb. The disposable session has its own
GNOME credential service and private home. The journey initializes the native
vault through Settings, reviews two offline personal contexts, switches views,
restarts the app and compares the retained state with the installed bundled CLI.
It verifies the default credential store and preserves unrelated home files.
Three fresh private sessions must each pass the complete journey. The external
driver uses one persistent HTTP connection; failed UI commands are not replayed.
Those three journeys qualify personal contexts. A separate mandatory Linux
journey uses the same installed package and driver with an isolated actual
API/PostgreSQL: named OS-vault enrollment, synthetic browser approval, corporate
context creation, registered checkout review, explicit request/confirmation,
lost committed reply, application restart, original-outcome reconciliation and
reviewed local binding adoption. Installed CLI, SQL rows and unowned files are
read back independently. Its separate proof does not qualify live SSO account
linking, harness installation or activation.

Release bundles require their own `cli/ai-stp-desktop-cli` resource. A missing
bundled engine fails closed. Development can use `AI_STP_CLI` or PATH when no
bundled resource is present; a missing configured executable also fails closed.
The compile-time stub never overwrites a real sidecar.

## Release

Tag the verified commit `desktop-vX.Y.Z`, matching all desktop manifest versions,
then dispatch `.github/workflows/desktop-release.yml` on that tag. The workflow
requires the exact current successful main qualification, then uses the same
three-OS Desktop workflow to check and package the release. Its installed Linux
journeys run against the published package before the six installers and
`SHA256SUMS` are uploaded. The publisher runs without a source checkout.
Bundles are currently unsigned; no signing credentials are configured.
