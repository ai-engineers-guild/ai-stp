# ai-stp Rust CLI

`ai-stp` is the native CLI engine. The Cargo package lives in `apps/cli`;
its library owns business operations and its executable renders envelope v1.
There is no Python fallback, model client, background updater or telemetry.
The executable registry is the command reference: `ai-stp help --agent --json`.
Use `task intents` and `task input-schema` for the smaller task interface.

## Release and supported platforms

Stable archives use `cli-v<version>` tags and the exact `Cargo.toml` version.
Builds target Linux x86-64 (Ubuntu 24.04), Apple Silicon (macOS 15) and Windows
x86-64 (Windows Server 2025). These CI environments define the tested baseline;
older operating systems are not implicitly qualified. Linux uses the system GNU
C runtime and Windows the Microsoft C runtime. macOS and Windows artifacts do
not carry an OS application certificate or notarization.

| Capability | Linux | macOS / Windows |
|---|---|---|
| Native metadata, source analysis, authoring, catalog, account, sync and publication | Implemented | Built and exercised by platform CI |
| Archive-owned CLI installation/update | Implemented | Exercised by platform CI |
| Isolated provider execution, setup installation and active-session handoff | Implemented | Unavailable; explicit refusal |
| In-place legacy state transfer | Real SQLite/WAL and interrupted file-credential proof | macOS file-credential proof; Windows rejects file credentials, native keyring adapter is compiled |

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

## Business services

| Modules | Implemented responsibility |
|---|---|
| `identity`, `account`, `migration` | Offline identity, native credential storage, device-code sign-in, refresh/logout, owner attachment, revoked-key recovery and explicit writer transfer |
| `sources`, `projects`, `authoring` | Bounded discovery and source capture, project evidence, component/setup authoring, revisions, exact versions, import/export, quality checks and conservative native transformations |
| `selection`, `bundle` | Mechanical compatibility, trust/access constraints, exact graph selection and deterministic scoped bundles |
| `provider`, `program` | Authenticated installation-component acquisition, user-installed harness observation, isolated configuration writing and recovery |
| `tasks` | Durable `author` and `install` intents over the same in-process services |
| `catalog`, `publication`, `sync`, `attestation` | Exact catalog acquisition, publication/visibility, grants, private revision exchange, conflicts, contribution reports and author attestations |
| `distribution` | Explicit native archive installation and update with owner-bound recovery |

`config show/validate` accepts only implemented network settings: `catalog.enabled`,
`catalog.url` and `sync.enabled`. Configuration is selected explicitly with
`--config`; sync requires `sync.enabled: true`. Account plans retain their exact
origin/provider. Unknown settings refuse rather than promising unused behavior.
No corporate cabinet, assignment/heartbeat/usage delivery, generic model evaluation
runner or automatic toolchain manager is included. Use the executable registry for the supported command surface.

## Setup components and installation

Setup systems are ai-stp installation components with separate public repositories
with a single CLI entrypoint. The CLI authenticates their exact releases and invokes them itself;
users do not install a second setup-manager product. `provider/managed.rs` owns
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
is not a global process-start lock. Only the public component writes final
harness state; no in-place half-update of the active agent is authorized.

## Build and verification

Rust 1.99.0 is pinned in `rust-toolchain.toml`. The SQLite capability VFS build
needs libclang (the selected Xcode toolchain on macOS, the Visual Studio Clang
component on Windows, or the system development library on Linux). The
repository-only Rust build tool in `xtask/` finds that installed toolchain; the shipped executable does not need libclang.

```sh
just cli-gen          # Refresh embedded shared contracts after back-gen
just cli-check
just desktop-check
```

The native gate runs formatting, Clippy, Rust tests, the optimized release build
and real envelope/SQLite regression. Builds, archive/SBOM/wheel packaging and
desktop resource probes use Rust.
The published source crate includes generated resources under `resources/`;
`just cli-gen` projects the shared sources and `cli-static` rejects drift.
Independent server interoperability proofs live in `tests/native_contract`;
they validate the native output against the actual Python server models in CI.
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
