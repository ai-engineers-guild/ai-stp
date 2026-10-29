# ai-stp Rust CLI

`ai-stp` is the native CLI engine. The Cargo package lives in `apps/cli`;
its library owns business operations and its executable renders envelope v1.
There is no Python fallback, model client, background updater or telemetry.
The executable registry is the command reference: `ai-stp help --agent --json`.
Use `task intents` and `task input-schema` for the smaller task interface.

The commands below describe the CLI 0.2 / Desktop 0.1 client line. Immutable
CLI 0.1.3 / Desktop 0.0.11 binaries retain their original command surface;
deploying the server does not update an installed client. Match the executable's
machine help and registry compatibility before using an operation.

`account providers --api-url https://your-server.example` reads the sign-in
methods enabled by that deployment without credentials or local state writes.
Machine help lists the engine's supported methods; it does not claim that a
server has configured them. Starting sign-in remains subject to server policy.

Retain independent server/account sessions with `account connections plan`
(`--label`, `--api-url`, `--provider`) and `account connections apply` using the
reviewed plan and digest. Each enrollment has its own remote device ID and native
credential slot; the offline authoring identity and existing session remain intact.
`account connections list` exposes metadata and any interrupted creation intent.
Use its exact `--connection` ID with account plan/status, private catalog version
reads, grants, GitHub source requests, visibility requests and report previews.
Their retained plans keep that original connection across view changes and retries.
Omitting the selector explicitly retains the legacy session behavior.

`publication plan`, `attestation plan` and private `sync push/pull plan` also
accept `--connection ID`. Ownership-sensitive operations require the registry's
explicit attachment to that account at that origin. An independent enrollment
of the same account can transport and sign; the native authoring device stays
unchanged. Matching account IDs at different servers grant no owner authority.
Publication resume resolves its original retained enrollment automatically.
Selection access JSON accepts `{"account":true,"connection":"connection_ID"}`;
its exact plan freezes that enrollment. A connection cannot invoke legacy local
device recovery. Device sync summaries name the remote enrollment device while
their observed platform facts still come from the native passport.

`registry acquire plan --private --connection ID` captures an exact private setup
graph from that connection's origin. Authorization uses its remote enrollment;
the local identity records acquired bytes without an owner or key transfer.

`account organizations --connection ID` reads available organizations; use
`--legacy-account` instead to explicitly read through the existing local-owner
session. `context create plan --legacy-account --label NAME` admits that session
as a context without creating another enrollment or copying its credentials.
Create a native offline context with `context create plan --label NAME`, or add an explicit
connection and organization for a server-resolved personal/corporate observation.
Apply the exact plan with `context apply`. `context select plan --context ID`
plans a revision-checked view preference; selection changes no harness files or
existing operation binding. `context list` and `context show` are local reads;
`context show --refresh` checks current access through the original connection.
Cached capabilities never authorize installation or publication.

After native identity recovery, a saved context can remain valid for historical
reads while its earlier identity cannot create a new checkout change. Such a
review returns `AI_STP_PRECONDITION_FAILED` with
`error.details.reason=historical_native_identity`. Review a fresh context for the same
account and company through the existing sign-in, apply its exact plan and select
it explicitly before reviewing a new checkout intent. Old contexts and original
receipts remain unchanged; selecting a view never transfers an admitted intent.

`corporate teams`, `corporate projects` and `corporate project show --project ID`
read through a saved corporate context. `corporate projects --membership-only`
uses the authenticated person's explicit project memberships; visibility alone
does not establish assignment membership. Corporate project IDs use the server's
`remote_project_` namespace, separately from local project passports.
`corporate technologies` and `corporate mappings list/show` read the organization's
own technology directory and versioned mappings. `corporate catalog search`
requests an authenticated organization-scoped page.
That page projects the public catalog's authoritative lane. An organization
assignment does not publish a private setup or make an experimental version
authoritative; private assigned coordinates are resolved separately in previews.

`corporate project link-target --project ID` reads the exact remote ledger head,
current immutable provider identities/revisions and authorization revision needed
by a separate server-authored link plan. It creates no link or local binding.
Provider duplicates, mixed coordinates and a policy revision inconsistent with
the current context refuse; incomplete provider observations must be refreshed.

`corporate project link-preview --project ID --root PATH` joins those current
coordinates with an existing owned private project passport and an attached,
committed Git checkout. Record the passport first with `project passport plan`
and `local apply`. Optional `--provider-project ID` selects an exact current server
provider identity; it is never guessed from a remote URL. `--git-executable` may
name an existing trusted Git executable. The preview keeps the original context
and enrollment and rechecks session, membership/policy, target revisions, physical
root, passport head and Git evidence. Switching the selected view cannot retarget
it. It sends no local passport, Git routing data or installation inventory.
Unregistered, unborn/detached or changed checkouts require explicit reconciliation.
The preview digest and request coordinates are observations: no idempotent request
is admitted, no server plan/link or local binding is created, and they cannot be
applied as an installation or confirmation plan.

`corporate project link-outcome --plan-id ID` reads the original account-owned
plan and its current ready, expired or applied outcome. Applied evidence includes
the exact retained link, including its current unlinked/conflict state. A fresh
device of the same account may recover this evidence; confirmation remains bound
to the original device. This read neither retries confirmation nor binds a local
checkout, and membership and policy are checked again for every observation.

`corporate project link-settlement --plan-id ID` waits on the server's original
confirmation barrier before reading the outcome. An older server's unsupported
response remains unknown. This observation does not release a native reservation;
an ordinary expired outcome cannot substitute for the settlement barrier.

If the original plan response was lost, use `corporate project link-request-outcome`
with `--request-key KEY` and that request's exact retained idempotency key. The read
finds only the same account's original plan; it does not submit or confirm it.
An absent result leaves an in-flight request unknown and cannot prove rollback.

`corporate project link-current --link-id ID` observes one exact current company
link through active membership and a context with `project.unlink`. It validates
the link ID/company, drops unknown fields and fences current authority before
and after the read. Linked, conflict and unlinked states remain observations;
the read does not identify an original unlink request, submit a mutation, retire
a local binding or grant installation authority.

`corporate project unlink-outcome --plan-id ID`, `unlink-settlement --plan-id ID`
and `unlink-request-outcome --request-key KEY` observe an original account-owned
unlink through its exact retained coordinates. They require current
`project.unlink` capability and preserve the current context/policy fences.
Settlement waits for the original confirmation barrier; applied evidence must
identify the exact unlinked relationship at the expected next revision. An
absent/unsupported response stays unknown. These reads submit no unlink and
release no local binding, reservation, task or harness files.

For an active native binding, `corporate project unlink-request plan
--binding-operation ID --context ID` reviews an original unlink-plan request.
Apply its exact JSON/digest with `corporate project unlink apply`; then review
`corporate project unlink-confirm plan --request-operation ID` and apply that
second plan. New writes require the original account/company, current capability,
registered physical checkout and unchanged reviewed source. All confirmation
reviews of one request share one operation/key slot. The first admitted digest
is fixed; applying an uncertain intent only reads its original result. A current
same-account replacement `--context` is a reader for admitted work and cannot
retarget an unused write plan. Completion keeps the local binding and reservation.

`corporate project unlink-retire plan --operation ID` separately reviews closing
an unknown request locally, preserving its unknown remote outcome. An uncertain
confirmation additionally requires a current same-account `--context` and exact
expired/unapplied server settlement, repeated at apply. Use `unlink-retire apply`
with that plan/digest. Ready, applied, forbidden, offline and unsupported results
retain the pending confirmation. This closes only intent; it never releases the
active binding, reservation, tasks or harness files. Completed and retired
receipts replay offline. First unlink admission atomically advances the native
writer epoch to 59; older writers refuse it, while supported 53–58 receipts remain.

Use `corporate project link-retire plan --operation ID` to review stopping a
retained unknown request locally. Its remote outcome stays unknown; the original
key and receipt remain. For an unknown confirmation, name its exact current
same-account `--context`: only a fresh serialized expired settlement without a
link can release its own unbound physical reservation. Ready, applied, forbidden,
offline and unsupported-server outcomes retain the reservation. Apply the exact
reviewed JSON/digest with `corporate project link-retire apply`. Terminal replay
is offline and cannot remove a later request's reservation. Active bindings need
separate unlink/reconciliation and cannot be retired through this command.

`corporate project link-request plan --context ID --root PATH --project ID`
reviews the original request without creating a remote plan. Apply its exact
JSON/digest with `corporate project link apply`. A separate
`corporate project link-confirm plan --request-operation ID` reviews the ready
server decision through its original device and a freshly observed checkout.
Apply that second exact plan to confirm. Retained intents keep their original
context, account/device, request key, policy and physical checkout across view
changes. After a lost response, applying the same intent reads its original
outcome; it never repeats the POST. A 404 preserves the unknown result.

After positive active-link evidence, `corporate project link-adopt plan
--request-operation ID --context ID --root PATH` reviews the local binding.
Its apply grants no installation authority. Confirmation reserves the private
project and physical checkout across all contexts until the original outcome
is reconciled. A missing checkout does not prevent outcome reconciliation or
offline replay of a completed receipt; adoption requires the original physical
checkout again. Use `corporate project link show/list` for retained local state
and `corporate project link outcome --operation ID` for a fresh observation.
An explicit matching replacement `--context` on an already admitted apply
only reads the original effect; it cannot admit the previous device's unused
confirmation plan. Binding retirement and relocation are separate operations;
an expired observation alone does not release a reservation.

`corporate project binding-retire plan --binding-operation ID --context ID`
reviews an original completed adoption after a fresh current-link read confirms
its exact immutable lineage is unlinked. Current `project.unlink` authority is
checked around the read and again at apply. Apply the exact JSON/digest with
`corporate project binding-retire apply`. The original physical checkout and
private passport must still match; pending unknown checkout/unlink writes refuse.
The atomic writer60 transition preserves the original adoption/request receipts,
updates only that cached link and releases only its exact reservation. It changes
no tasks, targets or harness/checkout files. A separate new request may bind again;
the old request cannot be adopted with a fresh nonce. Reapplying a completed
retirement replays its historical receipt offline and cannot release a future
binding. Keep a qualified60-compatible engine; writer59 refuses the newer epoch.
`corporate project link show` returns the original adoption receipt together with
its separate `binding_retirement` receipt, or `null` before local retirement.
This history read does not reopen the checkout, contact the server or inspect a
future independent binding. Completed apply replay retains its original output.
Ordinary project passport observation may
relocate an unreserved private project. A retained corporate reservation blocks
changes to its logical ID, physical root or registered location during planning
and apply, including a plan reviewed before the reservation was admitted.
Recreating the old pathname does not permit assigning a new ID to the reserved
physical checkout. In-place observation and registration of a physically distinct
private copy remain available. Observation preserves the original adoption
receipt and never releases the reservation.

For a reviewed same-object move, first review `corporate project location-anchor
plan --state-dir PATH --context ID --binding-operation ID` while the registered
checkout is present, then apply its exact JSON/digest with `corporate project
location apply`. The terminal anchor records full physical checkout and embedded
`.git` identities. After that command returns and closes its handles, move the
directory yourself. Review `corporate project location-relocate plan` with the
same state/context/binding coordinates and `--root DESTINATION`, then apply that
exact plan. The previous pathname must be absent; physical identity, attached
branch, commit, configuration and routing must still match the trusted location.
Keep the native state directory outside the checkout; moving the checkout must
not also move the registry that records its location.
Current `project.link` authority in the original company is required; moving
local metadata does not require `project.unlink` or create installation authority.

The operation commits only the private passport/location and its terminal receipt
in the protected registry. Original adoption/request receipts, reservation,
marker, user files and tasks remain intact. Completed location replay is offline
history and cannot retarget a future location. Unfinished task roots must be
physically disjoint. Retained related provider targets require their separate
context-owned reconciliation before this metadata-only move; opaque unfinished
legacy installations refuse. A missing or replaced unfinished root is not assumed
disjoint. Cross-volume copies, remapped/external Git directories, missing-root
recovery and revoked-authority offboarding are not supported by this transition.
`corporate project location show --state-dir PATH --operation ID` recovers a
completed receipt after losing its local response or plan file. `location list
--state-dir PATH --binding-operation ID` pages that original binding's history;
pass the returned `next_cursor` as `--cursor` for the next page. These reads do
not reopen a checkout or refresh a server session.

Location admission advances the native writer epoch to 61. Keep a qualified
61-compatible engine for that registry; the immutable released CLI 0.2.1 supports
through 60 and refuses the newer state. Older receipts retain their original
encoding, and no read silently upgrades or downgrades a registry.

These commands accept `--context ID`; omission resolves the selected view once
for that new read. The result retains its original context, current account
revision and bounded observations. Changing the view during a delayed reply does
not change its server or organization. Membership/capabilities are checked before
and after the read; changed authority refuses the observation. Unknown server
extensions are excluded, including nested fields. No corporate response is
persisted as an authorization cache.

`corporate assignments preview --harness ID` supports all seven harnesses and
optional `--project`/`--technology` coordinates. It sends an explicitly empty
managed inventory, without personal or other-context installations. Its server
diff and observation digest cannot be applied as an installation plan. Checkout
linking, context-owned installation receipts and actual corporate delivery remain
separate operations.

`project checkout inspect --root PATH` observes a Git checkout without an account,
registry or marker. Git remains user-managed; `--git-executable /absolute/path`
selects an existing trusted executable when ordinary PATH discovery is unavailable.
The bounded local queries disable prompts, optional locks, lazy fetch and Git
transport protocols, and exclude ambient Git overrides and global/system config.
Repository config includes refuse; enabled worktree config is observed separately.
Remote/routing values appear only as opaque fingerprints, never as raw URLs.

The result separates physical root/Git directory/common-directory identities,
branch and routing topology from the current SHA-1/SHA-256 commit. An ordinary
commit on the same branch changes the observation but preserves the topology
digest; relocation, replaced roots, branch/detached changes and remapping do not.
Two matching reads detect observed races; this is not a filesystem lock or a
provider confinement boundary. Name each nested repository's own root explicitly.
Unborn and detached states are observations, not authorization to enroll them.
No provider repository identity is inferred and no local/corporate binding or
installation authority is created.

`just cli-corporate-regress` runs the optimized native engine against a real
loopback API and a disposable PostgreSQL database selected by
`AI_STP_TEST_DB_URL`. Linux CI runs this gate without an optional skip. Only
approval of synthetic device codes is supplied by the fixture; enrollment,
session isolation, corporate reads and seven-harness previews use the actual
HTTP contracts. It also withholds committed create/confirmation replies and
checks original-outcome recovery, named/root device replacement and reviewed
binding adoption. The fixture never connects a live SSO account or runs a harness.

The first applied connection/context plan explicitly upgrades the same authority
registry to schema 55. Older clients refuse that format; keep a compatible client
available. No database copy, key rotation, credential copying or implicit owner
attachment occurs. The legacy global attach/recover actions do not operate on a
named enrollment.

`account connections recovery plan --connection ID --label LABEL` reviews a
replacement for a named session whose status records `device_revoked`, or whose
retained authorized session has a genuinely absent enrollment key. Version 1
binds the original authorized account receipt and positive revocation receipt.
Version 2 records key absence with the retained session receipt; absence is
rechecked before admission. Corruption or an unavailable credential store is an
error, not evidence of absence. Both versions fix the exact new connection/key
operation. `account connections recovery apply` explicitly
admits schema 56 and both recovery and key creation in one registry commit.
The child key plan cannot be applied separately before its parent admission.
Use `account connections recovery list` to resume `creating_key` or inspect
`sign_in_required` and the eventual `authorized` receipt. Admitted key creation
can resume after plan expiry; an existing ready key is never silently replaced.

Sign in through the reported replacement connection. Every authorization fixes
the expected account and revoked public key, including later reauthorization.
The server must accept that same account with a distinct replacement key and
prove the previous key is revoked before the native recovery completes. A
missing local key permits preparation only: authorization still refuses while
the previous server device is active. A stored positive receipt finishes confirmation
after an interruption without repeating the single-use exchange. Original
credentials, local identity and saved contexts retain their identities; create
new context views explicitly through the replacement connection. New requests
through the retired enrollment refuse, while exact historical receipt replay
remains available.

Version 3 additionally binds exact unfinished publication/sync checkpoints from
the original enrollment. Their local interruption and recovery admission commit
together. Original wire requests and idempotency keys remain unchanged, and the
interrupted result explicitly retains `remote_outcome: unknown`. Unrelated
enrollment operations are retained. Empty checkpoint fields remain omitted from
version-1/2 plans, preserving their serialization and digests.

After replacement sign-in, `publication reconcile --connection ID --operation-id ID`
reads remote evidence through a confirmed same-account replacement chain. It
never resumes old-device writes or changes historical interruption receipts.
`sync recover plan --connection ID --event-id ID` reviews local retirement of one
pending request covered by that verified chain. Applying the plan preserves its
bytes and unknown remote outcome; it does not create a server acknowledgement.
A later pull can still observe the actual accepted event.

Schema 56 preserves the original database filename and production owner marker;
older clients refuse unsupported recovery records. Recovery does not settle
unknown remote effects or grant corporate installation authority.

The first checkout mutation admission explicitly upgrades that same registry to
schema 57, atomically with its original intent and any physical reservation.
Format-55/56 retained profile and recovery plans keep their original encoding;
new enrollment recovery at format 57 uses version 4 and captures original
checkout checkpoints. Root and named recovery retire the original writer while
retaining unknown effects and reservations. A current authorized context may
read positive original evidence afterward; that read does not restore old-device
write authority. No registry copy, automatic relinking or harness write occurs.

Reviewed checkout retirement advances the registry atomically to format 58,
fencing older writers before releasing a settled reservation. Original plans,
keys and format-55–57 receipts keep their bytes. New checkout plans use version 2
and new enrollment recovery uses version 5 on format 58; neither profile changes
nor recovery can downgrade it. Unknown request retirement closes only the local
intent and makes no claim about its remote effect.

Windows account sessions use versioned compressed binary records in the native
Credential Manager, avoiding its password API's UTF-16 expansion. The native
blob is limited to 2,560 bytes and decoded records to 64 KiB; records that cannot
fit refuse before credential publication. Existing password entries remain
readable and device keys retain their encoding. New session writes fence older
account-journal readers; retain a compatible client. No token file fallback is
used.

## Release and supported platforms

Stable archives use `cli-v<version>` tags and the exact `Cargo.toml` version.
Builds target Linux x86-64 (Ubuntu 24.04), Apple Silicon (macOS 15) and Windows
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

## Business services

| Modules                                         | Implemented responsibility                                                                                                                                                          |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `identity`, `account`, `migration`              | Offline identity, native credential storage, device-code sign-in, refresh/logout, owner attachment, revoked-key recovery and explicit writer transfer                               |
| `sources`, `projects`, `authoring`              | Bounded discovery and source capture, project evidence, component/setup authoring, revisions, exact versions, import/export, quality checks and conservative native transformations |
| `selection`, `bundle`                           | Mechanical compatibility, trust/access constraints, exact graph selection and deterministic scoped bundles                                                                          |
| `provider`, `program`                           | Authenticated installation-component acquisition, user-installed harness observation, isolated configuration writing and recovery                                                   |
| `tasks`                                         | Durable `author` and `install` intents over the same in-process services                                                                                                            |
| `catalog`, `publication`, `sync`, `attestation` | Exact catalog acquisition, publication/visibility, grants, private revision exchange, conflicts, contribution reports and author attestations                                       |
| `distribution`                                  | Explicit native archive installation and update with owner-bound recovery                                                                                                           |

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
Direct apply also checks observed consumers when its caller uses a different
configuration home, including the desktop's filtered CLI environment.

## Build and verification

The manual `provider-release-qualification` workflow authenticates an exact
seven-component release and reads its declarations under measured Linux
isolation on Ubuntu 24.04. It requires project profiles and compares each
artifact's source with its published tag. Its public JSON observations support
release review and catalog updates; they are not installation permits or proof
of configuration application. Provider execution and report generation stay in
the disposable CI environment.

Rust 1.99.1 is pinned in `rust-toolchain.toml`. The SQLite capability VFS build
needs libclang (the selected Xcode toolchain on macOS, the Visual Studio Clang
component on Windows, or the system development library on Linux). The
repository-only Rust build tool in `xtask/` finds that installed toolchain; the shipped executable does not need libclang.
Linux tests also require `dbus-daemon` for a private bus with no service activation;
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
