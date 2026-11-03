# ai-stp Rust CLI

The native engine owns authoring, exact configuration graphs, installation,
accounts and local state. It calls no model API and needs no model key or Python
runtime. The executable is the command reference:

```sh
ai-stp init --credential-store os_keyring --json
ai-stp help --agent --json
ai-stp task intents --json
ai-stp task input-schema --intent install --json
```

Read `capabilities --json` before planning a platform-specific operation. Commands
return envelope v1; see [JSON](../../docs/contracts/cli-json.md) and
[configuration](../../docs/contracts/cli-config.md). Match the installed engine's
machine help; a server deployment does not update an installed client.

## Release and supported platforms

Stable archives use `cli-v<version>` tags and the exact `Cargo.toml` version.
Builds target Linux x86-64 (Ubuntu 26.04), Apple Silicon (macOS 15) and Windows
x86-64 (Windows Server 2025). These CI environments define the tested baseline;
older operating systems are not implicitly qualified. Linux uses the system GNU
C runtime and Windows the Microsoft C runtime. macOS and Windows artifacts do
not carry an OS application certificate or notarization.

| Capability                                                                          | Linux                                                 | macOS / Windows                                                                                   |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Native metadata, source analysis, authoring, catalog, account, sync and publication | Implemented                                           | Built and exercised by platform CI                                                                |
| Archive-owned CLI installation/update                                               | Implemented                                           | Exercised by platform CI                                                                          |
| Isolated provider execution, setup installation and active-session handoff          | Implemented                                           | Unavailable; explicit refusal                                                                     |
| In-place legacy state transfer                                                      | Real SQLite/WAL and interrupted file-credential proof | macOS file-credential proof; Windows rejects file credentials, native keyring adapter is compiled |

`capabilities` reports the running platform and installation boundary. Build
success is not a claim that an unavailable provider sandbox works on that OS.
Harness executables are user/vendor managed: ai-stp observes the installed
version and exact program identity, but never installs, pins, updates or removes
the harness. Exact setup and installation-component versions remain immutable.

Each archive contains `ai-stp` (`ai-stp.exe` on Windows), `LICENSE`,
`ai-stp-cli.cdx.json` and `release.json` schema 2. The manifest binds the source
commit, target and payload hashes. The CycloneDX 1.6 SBOM describes the locked
reachable Cargo normal/build dependency graph; it is not a linker inventory of
OS libraries, compiler internals or all bundled C sources. Packaging is compared
byte for byte from the same executable; cross-machine reproducible compilation
is not claimed. Checksums and GitHub artifact attestations cover published files.

Verify the checksum and attestation for `ai-engineers-guild/ai-stp` with signer
`.github/workflows/cli-release.yml` before extracting or executing a download:

```sh
gh attestation verify <archive> --repo ai-engineers-guild/ai-stp \
  --signer-workflow ai-engineers-guild/ai-stp/.github/workflows/cli-release.yml
```

The release workflow runs contract/SQLite proofs against the extracted executable
outside the checkout, with an empty PATH and isolated home. Release receipts and
exact workflow identities belong to the GitHub release and its source PR.

## Install and update

Run the verified archive executable outside its intended installation directory:

```sh
./ai-stp cli install plan --prefix /absolute/private/ai-stp-cli --json
```

Save `data.plan` to a JSON file, review it and apply its exact digest:

```sh
./ai-stp cli install apply --plan install.json --plan-digest sha256:<digest> --json
./ai-stp cli install status --prefix /absolute/private/ai-stp-cli --json
```

The parent must already exist. The installer binds that parent, the old binary
receipt, the new digest/version/platform and a durable intent before atomically
replacing the executable. It refuses package-manager, shared-bin and desktop
prefixes, external drift and version downgrades. A later verified archive uses
the same operation. Pending plans resume after interruption; a published binary
is read back before the final receipt. Windows may require closing an existing
CLI process before retrying replacement.

PATH, credentials, the registry and harness configuration are untouched. Expose
the reported executable through a user-owned PATH directory or command link.
PyPI distributes these same native binaries in the `ai-stp` package, without
Python wrappers or runtime dependencies: `uv tool install ai-stp` or
`pip install ai-stp`. The package manager owns subsequent updates. The older
`ai-stp-cli` PyPI project is separate; remove its launcher through its package
manager before installing `ai-stp`. Never force-overwrite another tool
installation. The source crate is `ai-stp-cli`: `cargo install ai-stp-cli --locked`
requires the Rust and native compiler prerequisites below.
For an archive-managed installation, retire the old launcher through its owning
package manager before exposing the new command. Never overwrite its launcher.
There is no automatic download, backup, database restoration or implicit
privilege escalation.

## State and first run

State-taking commands accept `--state-dir`. Otherwise the CLI uses
`AI_STP_STATE_DIR`, then `$XDG_DATA_HOME/ai-stp`, with
`$HOME/.local/share/ai-stp` as the XDG fallback. This preserves the previous
cross-platform location. `state path`, `doctor` and metadata reads create nothing.
`capabilities` lists readable registry and snapshot schemas 53–56. `snapshot inspect`
reads an explicitly supplied standalone SQLite backup with its exact SHA-256 digest.

```sh
ai-stp init --credential-store os_keyring --json
ai-stp device show --json
ai-stp task intents --json
```

Initialization explicitly creates a private directory and resumes the existing
identity plan/apply journal. Repeating it preserves the owner and device key;
a different credential backend refuses. Unix users may explicitly choose `file`,
which is private but unencrypted. It is never an automatic keyring fallback.
The Windows file backend is unavailable.
An explicit state directory does not create another operating system vault.
macOS uses the existing User/login Keychain; its failure details contain only
the credential stage and numeric OSStatus, without native error prose.

Existing Python state cannot be initialized as another owner. Transfer it with
`state migrate plan --state-dir <root> --credential-store <existing-backend>
--provider <existing-provider>` and `state migrate apply --plan <file>
--plan-digest <digest>`. The provider is explicit because the old session format
did not retain it. Planning binds the physical database, complete row generation,
owner, device/public key and credential metadata. Unfinished legacy tasks,
operations, installation or self-update journals and pending browser login refuse.

Transfer keeps the original SQLite file and all 51 tables in place. Admission
atomically stamps schema 54 with its operation, fencing old schema-53 writers.
Credentials move only after exact readback; the old key/session slots are then
retired. Native operations refuse partial ownership. The retained plan resumes
after interruption, including after admission expiry. A completed replay does not
replace later native records. Settled legacy tasks are read-only history. No
snapshot, cloned database or target restoration is made. Fresh native registries
retain the schema-53 data model; existing internal namespace markers remain
stable storage identifiers, not a second product.

## Contexts and recovery

`account providers --api-url URL` reads a server's enabled sign-in methods.
Create independent enrollments with `account connections plan/apply`; retain their
exact connection IDs for account, private catalog, publication and sync operations.
A different server or selected view never transfers an existing operation.

`context create plan` supports offline, personal and corporate views. Use
`--legacy-account` to review the existing session without another enrollment.
Apply the reviewed plan with its digest, then explicitly select the context.
Selection is a UI preference; cached membership/capabilities grant no authority.
A saved context after identity recovery can read history, while new protected
work requires a fresh review through the same current account/company.

Corporate commands read current projects, assignments, mappings, catalog and
heartbeat policy. Checkout linking, adoption, unlinking, retirement and relocation
use distinct reviewed plans and receipts. An uncertain reply retains its original
operation/reservation: inspect the outcome and settlement before retrying. Location
reconciliation records an already moved physical checkout; it moves no files.
Missing-checkout retirement requires positively unlinked remote evidence and the
original inspectable parent. Never infer completion from an absent/offline result.

`task status/list` identifies personal author/install tasks by their original local
account/device. Company selection does not turn these receipts into corporate
installation inventory. Legacy records without ownership remain unclassified.
Foreground corporate heartbeat requires explicit reviewed local consent and current
policy; disable works offline. Reporting contains only its declared fields and does
not infer harness activity or install a scheduler. The
[configuration contract](../../docs/contracts/cli-config.md#foreground-corporate-heartbeat)
owns delivery settings.

## Business services

The `identity/account/migration` modules own credentials and writer admission;
`sources/projects/authoring` own local evidence and exact versions;
`selection/bundle/installation` own graph compilation and configuration transactions;
`provider` preserves authenticated external-operation compatibility; and
`catalog/publication/sync/attestation` own exchange and publication. `tasks` composes
these same services; `distribution` owns explicit archive installation/update.

`config show/validate` accepts only `catalog.enabled`, `catalog.url` and
`sync.enabled`; select configuration explicitly with `--config`. Unknown settings
refuse. Corporate setup application and managed inventory are not enabled by a
personal task or a read-only assignment preview. Harness programs remain managed
through their vendors' official commands.

## Setup components and installation

Setup configuration is first-party ai-stp functionality. The native
`installation` library owns forward transactions, original physical bindings,
no-follow file publication, cancellation and retained outcomes. Its source
provenance and notice are retained beside the implementation. It carries no
harness executable installer, vendor artifact/version table or updater control.
Harness installation and updates belong to the vendor's official commands.

`installation::profiles` resolves the compiled configuration scopes for the local
execution platform. `bundle::compile_native` uses the shared exact-graph,
eligibility, projection and contribution compiler without an external provider
declaration. The shared package reader verifies the exact native profile and complete source
payload. Compilation and reading create no harness state or installation authority. Profile lookup has no fallback between global, user-root and project
scopes; the unclassified harness placeholder cannot select an installation engine.

`installation::planning` captures a separate native observation format with the
original context, exact graph/profile/eligibility inputs and full physical roots.
It preserves raw path spellings and file preconditions without before-images or
configuration writes. Corporate plans require a positively linked original
checkout and fresh exact assignment/policy observations. Context selection cannot
retarget the plan. This library format does not enable a new installation route;
protected effects still require separately qualified custody and authorization.

Existing `provider` commands still use the released external-component
compatibility path; integrating the library does not change an old operation's
identity or silently activate a new installation route. The CLI authenticates
those exact legacy releases and invokes them itself; users do not install a
second setup-manager product. `provider/managed.rs` currently owns
the build default. An explicit component release remains exact, and a retained
operation never floats to a new release. Full publisher identity, signed
environment, digest, profile and protocol checks precede invocation.

The native `install` task takes a closed JSON input from `task input-schema`:
exact setup coordinates, harness, one to three explicit roots and operation.
The task retains compiler/configuration plans and child receipts. It does not
implicitly select a setup. Each component prepares before publication; partial
publication requires forward recovery. Lost final task receipts recover the
original operation without source ZIPs. Cancellation before publication unwinds
preparation; committed work is reconciled, not guessed to be cancelled.

An active Linux harness uses `activation: "handoff"` or the explicit
`configuration set prepare/apply/confirm` flow. It stages all roots, observes old
consumers exiting, publishes while stopped and confirms from a newly started
consumer. Unsupported launchers must be stopped explicitly. Process observation
is not a global process-start lock. Existing compatibility operations retain their original component writer;
no in-place half-update of an active agent is authorized.
Direct apply also checks observed consumers when its caller uses a different
configuration home, including the desktop's filtered CLI environment.

## Build and verification

The manual `provider-release-qualification` workflow authenticates an exact
seven-component release and reads its declarations under measured Linux
isolation on Ubuntu 26.04. It requires project profiles and compares each
artifact's source with its published tag. Its public JSON observations support
release review and catalog updates; they are not installation permits or proof
of configuration application. Provider execution and report generation stay in
the disposable CI environment.

Rust 1.99.1 is pinned in `rust-toolchain.toml`. The SQLite capability VFS build
needs libclang (the selected Xcode toolchain on macOS, the Visual Studio Clang
component on Windows, or the system development library on Linux). The
repository-only Rust build tool in `xtask/` finds that installed toolchain; the shipped executable does not need libclang.
Linux wheel packaging requires binutils `readelf` to verify the declared glibc
floor against the actual executable. Linux tests also require `dbus-daemon` for a private bus with no service activation;
the cleanup regression does not use the user's session bus or services.

```sh
just cli-gen          # Refresh embedded shared contracts after back-gen
just cli-check
just desktop-check
```

The native gate runs formatting, Clippy, Rust tests, the optimized release build
and real envelope/SQLite regression. Builds, archive/SBOM/wheel packaging and
desktop resource probes use Rust.
Cargo build messages identify the executable used by regressions, release archives
and desktop sidecar packaging. A checkout-local `target/` is not required. Existing
managed Cargo/uv/Bun frontends, including the NDS Cleaner profile, retain their
shared caches and selected compiler; do not add a second cache-placement policy.
Use only the host owner's approved network-cache contract; keep private endpoints
and client configuration outside the repository. With the existing managed Cargo
frontend, `cargo metadata --manifest-path apps/cli/Cargo.toml --locked --offline
--no-deps --format-version 1` reports the effective `target_directory` and
`build_directory` from the repository root. Consume these fields directly rather
than constructing cache paths. If the pinned compiler or its admitted lane is
unavailable, stop without installing a toolchain or changing the shared profile.
Frozen release artifacts stay outside mutable build caches. Native GC and NDS
Cleaner own cleanup after ownership, leases and 72 hours of idle use are verified;
installed environments and application state are not idle cache entries.
The CLI regression keeps its Python validation environment in the user data
directory under `uv/projects`, isolated by checkout identity. An explicit
`UV_PROJECT_ENVIRONMENT` takes precedence. Package downloads remain in uv's managed
cache, and changing checkouts does not retarget another checkout's editable imports.
The libclang adapter uses Cargo's effective artifact directory. CI exercises native
checks with artifacts outside the checkout on Linux, macOS and Windows.
Pull requests run all-target native Clippy and library units on all three OSes.
All three execute the owned-slot native credential and independent CLI-process
cases. Linux uses a disposable Secret Service bus with 200 fresh concurrent
clients and 10 rounds in PRs; full main retains all 100 rounds, complete native/API
interoperability, packaging and installed desktop journeys.
The macOS observer checks exact slot presence without decrypting another
executable's secret; successive CLI processes read and revalidate their own keys.
The fixture never changes Keychain access control.
Run the native CLI locally through that profile. Build and run backend, web and
docs changes on the production server; desktop bundles are qualified in CI.
The published source crate includes generated resources under `resources/`;
`just cli-gen` projects the shared sources and `cli-static` rejects drift.
Independent server interoperability proofs live in `tests/native_contract`;
they validate the native output against the actual Python server models in CI.
The Linux job also runs `verify_ownership.py` against migrated PostgreSQL and the
HTTP API, acquiring an exact setup before and after repeated component ownership
transfers. For server-side qualification, set `AI_STP_TEST_DB_URL` to a disposable PostgreSQL
server with database creation rights and run `just cli-ownership-regress`.
Native child processes run without Python on PATH. `tests/startup.rs` proves
read-only first-run behavior and refusal to replace a legacy identity.
`tests/distribution.rs` proves archive ownership, replay, a modeled interrupted
publication and foreign-prefix refusal.
`tests/native_contract/verify_migration.py` includes
real process termination across the writer-transfer boundary on Unix.

Release builds use thin LTO and stripped symbols. Benchmark the optimized
executable in an isolated home; do not infer startup performance from debug
builds. Desktop bundles this same native executable and remains a process-contract
client. Its UI and gates are documented in `apps/desktop/README.md`.
