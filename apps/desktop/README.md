# ai-stp desktop

A Tauri 2 client of the bundled, optimized Rust CLI. The engine owns business
operations, credentials, SQLite state and harness configuration. The webview
receives public JSON envelopes. Harness programs remain user/vendor managed.

## Use

| View | Responsibility |
| --- | --- |
| Overview / Settings | Read health, identity and capabilities; explicitly initialize the chosen credential store. Existing Python state needs the CLI's reviewed in-place migration. |
| Connections | Create/recover independent enrollments and offline/personal/corporate contexts through exact plans. Review registry upgrades before application. |
| Catalog / Setups | Search the catalog, choose exact setup coordinates, author components and start personal installation tasks with explicit authorization. |
| Activity | Inspect original tasks and corporate checkout operations, retained plans, outcomes and recovery after restart. |
| Account | Discover server-supported sign-in, authorize in the browser and inspect/refresh the original enrolled session. |
| Company | Read projects, mappings, catalog and assignment previews; review separate checkout linking/adoption/retirement/location operations. |
| Targets / Discovery / Commands | Use the connected engine's descriptors with read/plan/apply gates and explicit apply confirmation. |
| Diagnostics | Enable an optional bounded in-memory trace and explicitly copy a content-free diagnostic report. |

Context selection is a view preference. Existing tasks and mutations retain their
original account/device/context, even after navigation or restart. Personal task
receipts do not establish corporate installation inventory. Cached company reads
and assignment previews grant no installation authority; unsupported platform
operations refuse according to the engine's capabilities.

If a start or apply reply is uncertain, inspect its original retained operation
in Activity before starting again. Identical interrupted task starts keep their
retry identity while the app is running. Choosing a separate request does not
cancel the original. Failed task reads remove stale controls until an explicit
successful read. Account/task responses from earlier visits cannot change the
current view.

Checkout adoption, retirement and location changes have distinct receipts.
Retiring a positively unlinked binding releases its reservation without deleting
files or changing harness configuration. Missing-checkout recovery requires the
original inspectable parent; relocation requires a previously reviewed physical
anchor and records an already moved directory. Inspect the original plan/outcome;
unknown, replaced or conflicting targets refuse. The
[CLI guide](../cli/README.md#contexts-and-recovery) describes the shared boundary.

Company heartbeat is separately enabled by server policy and reviewed local
consent. Only the focused app processes due foreground reports for the selected
corporate context. Personal selection, hiding/unfocusing the app or offline local
disable stops new passes. Pending retries retain original bytes/timestamps;
unsupported usage and installation observations remain unknown. No startup
service or reporting scheduler is installed.

Diagnostic copies include application/platform metadata, call timing, outcomes
and error codes. They omit local paths, command arguments/replies, error prose,
account codes and private task content. No automatic diagnostic upload occurs.

## Code

- `core/` resolves the engine and runs bounded processes with a filtered environment.
  Linux retains the existing session bus for OS keyring access. A timeout leaves
  effects unconfirmed.
- `src-tauri/` owns async IPC, serialized mutations and private temporary plan/input
  files, removed after use. Form objects are bounded to 16 KiB; the CLI validates them.
- `src/transport.ts` is the IPC boundary; `store.ts` shares engine state and
  `taskStart.ts` retains a logical start's retry identity. Common components use
  shared theme roles, vendored IBM Plex fonts, visible focus and reduced motion.

## Develop and verify

Use the repository's pinned Rust/Bun and the existing managed toolchains/cache.
Tauri needs the native webview development packages. From `apps/desktop`,
`bun run tauri dev` starts the app; frontend-only `bun run dev` has no native IPC.

```sh
just desktop-gen          # Format Rust
just desktop-check        # Frontend, Rust crates and actual optimized sidecar
just desktop-bundle-test  # Verify an existing packaged CLI resource tree
```

Release packages require `cli/ai-stp-desktop-cli`; missing bundled engines refuse.
Development may use `AI_STP_CLI` or PATH only when no bundled resource is present.
The compile-time stub never overwrites a real sidecar. Sidecar tests run the
actual CLI; UI unit tests isolate IPC responses. Installed application acceptance
and native platform qualification remain separate from compilation.

## Release

Tag the verified source `desktop-vX.Y.Z`, matching all desktop manifest versions,
then dispatch `.github/workflows/desktop-release.yml` on the tag. It checks/packages
Linux, macOS and Windows installers and publishes `SHA256SUMS`. Bundles are
unsigned; no application signing credentials are configured. Exact source and
qualification receipts belong to the GitHub release and source PR.
