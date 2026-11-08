# ai-stp desktop

A Tauri 2 client of the bundled, optimized Rust CLI. The engine owns business
operations, credentials, SQLite state and harness configuration. The webview
receives public JSON envelopes. Harness programs remain user/vendor managed.

## Use

Choose the installer for your OS from [Desktop 0.4.1](https://github.com/ai-engineers-guild/ai-stp/releases/tag/desktop-v0.4.1)
and verify it against `SHA256SUMS`. The app bundles CLI 0.3.0. The installed engine
reports its platform capabilities in Overview.

| View | Responsibility |
| --- | --- |
| Overview / Settings | Read health, identity and capabilities; explicitly initialize the chosen credential store. Existing Python state needs the CLI's reviewed in-place migration. |
| Connections | Create/recover independent enrollments and offline/personal/corporate contexts through exact plans. Review registry upgrades before application. |
| Catalog / Setups | Review/download an exact public catalog graph, choose the local setup and review file changes, prepare/apply/recover its original native operation, and inspect ownership, removal or missing-folder recovery. Create components from local files. |
| Activity | Inspect original tasks and corporate checkout operations, retained plans, outcomes and recovery after restart. |
| Account | Discover server-supported sign-in, authorize in the browser and inspect/refresh the original enrolled session. |
| Company | Read projects, mappings, catalog and assignment previews; review separate checkout linking/adoption/retirement/location operations. |
| Discovery / Commands | Inspect the engine's descriptors and advanced read/plan/apply operations with explicit apply confirmation. |
| Diagnostics | Enable an optional bounded in-memory trace and explicitly copy a content-free diagnostic report. |

Context selection is a view preference. Existing tasks and mutations retain their
original account/device/context, even after navigation or restart. Personal task
receipts do not establish corporate installation inventory. Cached company reads
and assignment previews grant no installation authority; unsupported platform
operations refuse according to the engine's capabilities.

Overview offers the next action for this device: initialize its credential store,
create a context, or find a setup. Choose **Find a setup** in the sidebar, review
and download a catalog version, then follow **My setups** to choose its folders.
The system folder picker and full-path entry both select existing directories.
Reviewing a setup writes no configuration files. Confirm its exact changes,
prepare it, stop the original tool sessions, then apply and restart as instructed.
Catalog coordinates stay available in a disclosure; replacement, adoption and
trust are separate advanced controls. Recovery keeps the original operation.

Discovery, Commands and Diagnostics are under **Advanced tools**. The main page
shows device diagnostics on request. Pages load when opened; the initial view
does not load every account, company and authoring screen.

If a start or apply reply is uncertain, inspect its original retained operation
in Activity before starting again. Identical interrupted task starts keep their
retry identity while the app is running. Choosing a separate request does not
cancel the original. Failed task reads remove stale controls until an explicit
successful read. Account/task responses from earlier visits cannot change the
current view. Native preparation is recovered in Setups after app restart;
completed operations remain inspectable in their original context. A new-session
confirmation never claims vendor loading or runtime health.

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

Company inventory has separate reviewed consent in Setups. Collection and exact-
batch delivery are explicit foreground actions, scoped to original native owned
receipts and current company policy. It sends no paths, contents or prompts and
does not claim complete discovery. Local disable retires unsent reporting.

Diagnostic copies include application/platform metadata, call timing, outcomes
and error codes. They omit local paths, command arguments/replies, error prose,
account codes and private task content. No automatic diagnostic upload occurs.

## Code

- `core/` resolves the engine and runs bounded processes with a filtered environment.
  Linux retains the existing session bus for OS keyring access. A timeout leaves
  effects unconfirmed.
- `src-tauri/` owns async IPC, serialized mutations and private temporary plan/input
  files, removed after use. Bounds depend on the operation (native requests 128 KiB,
  full native reviews 8 MiB); the CLI validates every object and digest.
- `src/transport.ts` is the IPC boundary; `store.ts` shares engine state and
  `taskStart.ts` retains a logical start's retry identity. Common components use
  shared theme roles, vendored IBM Plex fonts, visible focus and reduced motion.
- `src/i18n.ts` and `src/locales/` own the new workspace and setup guidance.
  Messages use ICU syntax and typed keys. The current English catalog is bundled
  offline; migration of the remaining views and the full language set is tracked
  in [#1372](https://github.com/ai-engineers-guild/ai-stp/issues/1372).

## Develop and verify

Use the repository's pinned Rust/Bun and the existing managed toolchains/cache.
Tauri needs the native webview development packages. From `apps/desktop`,
`bun run tauri dev` starts the app; frontend-only `bun run dev` has no native IPC.

```sh
just desktop-source       # Types, formatting and message syntax; no compilation
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
