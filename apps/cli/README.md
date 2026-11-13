# ai-stp Rust CLI

The native engine owns authoring, exact configuration graphs, installation,
accounts and local state. It calls no model API and needs no model key or Python
runtime. The executable is the command reference:

```sh
ai-stp init --credential-store os_keyring --json
ai-stp help --agent --json
ai-stp task intents --json
ai-stp configuration native pending --json
```

Read `capabilities --json` before planning a platform-specific operation. Commands
return envelope v1; see [JSON](../../docs/contracts/cli-json.md) and
[configuration](../../docs/contracts/cli-config.md). Match the installed engine's
machine help; a server deployment does not update an installed client.

## Release and supported platforms

Stable archives use `cli-v<version>` tags and match Cargo metadata.
Builds target Linux x86-64 (Ubuntu 26.04), Apple Silicon (macOS 15) and Windows
x86-64 (Windows Server 2025). These CI environments define the tested baseline;
older operating systems are not implicitly qualified. Linux uses the system GNU
C runtime and Windows the Microsoft C runtime. macOS and Windows artifacts do
not carry an OS application certificate or notarization.

| Capability | Linux | macOS / Windows |
| --- | --- | --- |
| Native metadata, authoring, catalog, account, sync and publication | Implemented | Native CI |
| Native configuration, physical custody and process handoff | Implemented | Native CI |
| Archive-owned CLI installation/update | Implemented | Native CI |
| Historical external-provider execution | Isolated compatibility route | Explicit refusal |
| Legacy state transfer | SQLite/WAL and file-credential proof | macOS file credentials; Windows requires its native vault |

Read `data.native_configuration` in `capabilities --json` for native setup support.
The top-level `configuration_installation` and `supported_harnesses` describe
the historical provider route.
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

Verify the published checksum. Set `ARCHIVE` to the downloaded file and check
its attestation before extracting or executing it:

```sh
gh attestation verify "$ARCHIVE" --repo ai-engineers-guild/ai-stp \
  --signer-workflow ai-engineers-guild/ai-stp/.github/workflows/cli-release.yml
```

The release workflow runs contract/SQLite proofs against the extracted executable
outside the checkout, with an empty PATH and isolated home. Release receipts and
exact workflow identities belong to the GitHub release and its source PR.

## Install and update

Choose a `cli-v<version>` archive for your platform from
[GitHub Releases](https://github.com/ai-engineers-guild/ai-stp/releases).
Verify it as described above, then run the extracted executable outside its
intended installation directory:

```sh
./ai-stp cli install plan --prefix /absolute/private/ai-stp-cli --json
```

Save `data.plan` to `install.json` and set `PLAN_DIGEST` to `data.plan_digest`.
Review the plan before applying it:

```sh
./ai-stp cli install apply --plan install.json --plan-digest "$PLAN_DIGEST" --json
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
`capabilities` lists readable registry and snapshot schemas. `snapshot inspect`
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

Transfer keeps the original SQLite file. Admission stamps schema 54 and fences
legacy writers. Exact credential readback precedes retirement of the old slots.
Resume the retained plan after interruption, including after admission expiry.
Settled legacy tasks are read-only. Native services can upgrade the registry as
needed. Inspect readable versions with `ai-stp capabilities --json`.

Newly authored OpenCode skills use their destination folder as the native ID;
frontmatter names are display metadata. Installation currently requires an
observed OpenCode 2.2.7. Other or unobserved versions refuse before configuration
writes. Retained projections and saved author plans keep their recorded identity
rules and exact immutable objects.

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

## Setup configuration

Use `configuration native` for new first-party configuration on all supported
platforms. It compiles an exact local setup graph for one to three existing
global, user-root or project folders. Compilation and review grant no later
execution rights. Harness programs stay user/vendor managed.

For a catalog setup, capture the exact version with `registry acquire plan` and
admit it to local state with `local apply`. Then save a configuration request
with the exact local setup coordinates:

```json
{
  "schema_version": 1,
  "setup": {
    "stable_id": "setup_…",
    "version": "1.0",
    "passport_digest": "sha256:…"
  },
  "harness_id": "codex",
  "operation": "install",
  "roots": {"global": "/absolute/configuration"},
  "trust": "exact_setup"
}
```

`trust: "exact_setup"` explicitly trusts the reviewed immutable graph; it does
not fabricate private access, company assignments or grants. Omit it to use
existing pins/ownership. Corporate input also requires its original checkout
binding; current company/project/source authority is checked before every effect.

```sh
ai-stp configuration native plan --context CONTEXT --input request.json --json
# Save data.plan as review.json; retain data.plan_digest.
ai-stp configuration native prepare --plan review.json --plan-digest DIGEST --json
ai-stp configuration native apply --operation OPERATION --plan-digest DIGEST --json
ai-stp configuration native status --operation OPERATION --plan-digest DIGEST --json
```

Use the original `--state-dir` throughout. `pending` recovers an admitted
operation without its plan file. `cancel` cancels unpublished preparation.
Recovery continues the original operation after partial writes across roots.

When `restart_required` is true, stop the observed harness sessions before apply,
start a new session afterwards and run `configuration native confirm` with the
original operation/digest/state directory. Confirmation observes a new process,
not vendor loading or runtime health.

`effective --context CONTEXT` reads current ownership and drift. Review updates
with `"operation": "replace"` in the same physical scope set. Use
`configuration native remove plan --operation OPERATION --plan-digest DIGEST`
for removal, followed by prepare/apply. Shared references and unowned fields/files
are preserved; conflicting or drifted ownership refuses. Custody belongs to the
OS user across state directories and ignores HOME/XDG selectors. `custody` explicitly inspects local ownership and original pending
recovery coordinates across state directories. For positively absent folders,
`configuration native retire plan --operation OPERATION --plan-digest DIGEST`
releases only their metadata references through prepare/apply. It preserves
history, live files and other owners; it grants no file or account access.

Explicit `"operation": "adopt"` accepts a terminal supported external 0.0.95
installation only when its original setup ID/version, ownership ledger and
actual values agree. Its old receipts and SQLite history stay unchanged.
Ambiguous owners and unfinished legacy work refuse. Historical `provider`,
`configuration set` and personal `task install` operations retain their exact
Linux compatibility route and immutable external-component identity.

Corporate inventory has separate consent:
`corporate inventory consent plan/apply`, `status`, `scan`, `flush` and `disable`.
It reports only actual owned native components, opaque locations and observed
file states under current company policy. Collection/delivery are explicit
foreground actions; retries keep the original batch. Local disable works offline.
It neither performs complete external discovery nor measures runtime loading.

Corporate runtime usage has its own reviewed consent:
`corporate usage consent plan/apply`, `status`, `record`, `flush` and `disable`.
`record` requires the original context, a current completed native installation
operation, an unchanged owned component, and a stable opaque signal ID.
The private outbox retains exact version coordinates and sends only content-free
events to the authenticated corporate usage endpoint. Exact retries are
idempotent; conflicting reuse of a signal ID is refused. Delivery is foreground
only. These manual reports are labeled `agent_reported`; no harness-native hook
collection or background service is available yet. Corporate native-hook
aggregates exclude these reports.

## Build and verification

Use the pinned Rust/Bun/uv and existing managed compiler/cache frontends. The
SQLite VFS build needs libclang; shipped executables do not. Linux packaging
also needs `readelf` to check the actual glibc floor, and credential tests use a
disposable Secret Service bus.

```sh
just cli-gen          # Refresh embedded shared contracts after back-gen
just cli-check        # Static checks, Rust tests, release binary and real SQLite contract
just desktop-check    # UI, Rust crates, actual optimized sidecar and resource probe
```

Consume Cargo metadata's effective artifact directories instead of inventing
target paths. Cache ownership, leases and cleanup belong to the managed frontend;
application state and installed environments are not build caches.
Published source includes generated `resources/`; `cli-static` rejects drift.

Native CI covers Linux, macOS and Windows. `tests/native_contract` checks real
server models and SQLite transfer; `enrollments_native` checks existing native
vaults and independent CLI processes. The manual `provider-release-qualification`
workflow remains an exact authenticated legacy-component proof. None of these
observations grants installation authority.

Release builds use thin LTO and stripped symbols. Desktop bundles the same
optimized executable; see [Desktop](../desktop/README.md). Release artifacts and
qualification evidence belong to their GitHub releases and source PRs.
