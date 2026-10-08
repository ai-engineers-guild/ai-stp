# ai-stp-cli-v2

Native preview of the ai-stp CLI. One Cargo package contains a headless library
and the `ai-stp-v2` executable. The supported production executable is still
`ai-stp`; this preview does not acquire production state or install harnesses.

```sh
just cli-v2-check
apps/cli-v2/target/release/ai-stp-v2 capabilities --json
apps/cli-v2/target/release/ai-stp-v2 help --agent --json
```

Install Rust through rustup; `rust-toolchain.toml` selects the toolchain.
`Cargo.toml` owns direct dependency choices and `Cargo.lock` owns the resolved
graph. Builds and checks use `--locked`. On Windows the executable has `.exe`.

## Contract

`registry.rs` owns command definitions, parsing, descriptors and the registry
digest. `help --json` is the current command reference; this document does not
duplicate its flags. Only implemented commands are advertised. No task intent
or supported harness is advertised at this checkpoint.

Machine mode returns one envelope v1 object on stdout, including refusals.
Exit classes and request IDs retain the existing wire contract. Human parser
help uses `--help`; in machine mode it returns the complete registry. A missing
command returns help. Error messages do not echo rejected argument values.

Preview `version` reports `runtime: rust` and `release_channel: preview`.
Preview `capabilities` reports explicit read-only snapshot access and readable
schema versions. They deliberately do not claim the Python-only version payload
or the production capability payload, which requires a supported harness.
Envelope and machine-help consumers are checked against the existing models;
preview payloads have no production result-schema URN. Default cutover still
requires a consumer-compatible version/capability contract.

The implemented metadata, configuration and snapshot commands are offline.
They do not discover production state, initialize a
device, open credentials, launch providers, refresh tokens or send housekeeping
requests. There is no Python or subprocess fallback in the native library.

Configuration reads use defaults unless an explicit YAML file is supplied.
They preserve the existing closed fields and report each value's source;
invocation overrides never write the file. The default registry location is
under `ai-stp-v2`, and no registry is opened by configuration commands. Unknown
keys, duplicate YAML keys, invalid types and unsupported schemas are refused
without echoing rejected values. Parsing is bounded to 1 MiB, eight levels and
10,000 events; file inclusion and environment interpolation are disabled.

`snapshot inspect` requires an explicit backup path and its `sha256:<hex>`.
Prepare it with SQLite's backup API and close the destination in DELETE journal
mode before hashing. A raw copy of a live WAL file is not a backup. The reader
checks the digest, loads those exact bytes into read-only in-memory SQLite,
checks integrity and reports table row counts without record contents. It
accepts schema 53 only, bounds the input to 128 MiB and limits SQLite work.
It never creates sidecars beside the source or applies migrations. Snapshot
origin is the caller's responsibility; a digest proves bytes, not who made them.

Local passport and version reads use the same explicit snapshot boundary.
They verify the embedded envelope schema, cross-field fact rules, content-derived
revision ID, row identity, parent links and immutable version digests. Conflicting
heads produce a conflict; reads never choose a winner or mint an identity.
The envelope schema is compiled into the binary from the generated repository
contract, with external schema retrieval disabled. No schema files or Python
installation are needed at runtime.

Project discovery and indexing require an explicit directory and never scan a
home or filesystem root. Reads use held directory handles and refuse symlinks,
special files and credential names. Indexes preserve the existing file classes,
SHA-256 and line counts; oversized files carry metadata only. Traversal is
bounded to 2,000 entries per directory, 20,000 observed entries, depth 12 and a
20-second work budget checked between filesystem operations. Slow filesystem
calls themselves are not cancellable. Exhausted or unreadable scopes report
incomplete evidence. Preview indexing excludes all symlinks, including internal
aliases that the Python reader accepted, to avoid raced credential aliases.

Public catalog reads use HTTPS (literal loopback HTTP is allowed for local
services), bounded timeouts and an 8 MiB response limit. Requests are anonymous,
with no redirects, ambient proxies or automatic retries. Search pages are live
only. Object and exact-version reads may use an explicitly supplied cache;
transient failures can fall back to a validated entry, while not-found,
authorization, transport-policy and invalid-body refusals remain refusals.
Cached answers retain their original `checked_at` and report `source: cache`.

The cache owns only its marked `ai-stp-v2-catalog` child below an existing
explicit directory, with an exclusive bounded lock, atomic replacements and
limits of 64 entries and 64 MiB. It does not import the production cache.
Entries bind the full endpoint URL, response digest and observation time;
passports additionally bind their published digest and requested coordinates.
Historical omitted fields with explicit schema defaults remain omitted, and
unknown passport fields and original strings are preserved. Revision hashes
are verified for local registry records; public snapshots instead retain the
published wire passport identity. Adaptations retain their complete-model
identity, ownership and case-folded path checks. Description validation uses
the closed CommonMark profile without rendering or extensions.

`environment requirements` joins exact setup/component passports from the
snapshot with the explicitly bound project target. It refuses a substituted
dependency, a copied marker whose original root still exists and ambiguous
project mappings. It reports environment-variable name presence without values;
authorization, managed harness and shared-program evidence remain
`not_observed`. Graph reads are bounded to 64 setups, 4,096 component documents
and 8,192 dependency edges. A moved-root read does not rewrite its old mapping.
The production `environment inspect` also calls provider/toolchain services;
that executable observation belongs to the provider slice, not this declaration
read. This preview result does not claim the production inspection schema.

`select graph` reads exact members or a saved proposal from the same snapshot.
It validates current component/setup version passports and their recorded
identities, then follows component requirements and setup members. Shared exact
dependencies expand once, with a deterministic dependency-first order and
shortest root distance. Drafts, tombstones, missing or substituted versions,
conflicting pins and incomplete closures refuse the whole graph; no partial
install order is returned. Limits are depth 32, 512 nodes and 8,192 edges.
Proposal inspection creates no session or object. Historical fact-only drafts
are not accepted as complete immutable version passports.

The headless `store` service owns an explicit `ai-stp-v2-state` directory with
private permissions, an ownership marker and a bounded process lock. Its clean
schema-53 bootstrap preserves the complete data format without historical
migrations. Unknown schemas are refused before writes; SQLite uses foreign keys,
defensive mode, an untrusted schema and FULL-synchronous WAL. Revision changes
check all expected heads inside `BEGIN IMMEDIATE`; content and revisions commit
or roll back together. Replaying a known revision preserves the current head.
Immutable snapshots never move draft heads. This service does not yet expose
authoring commands or import a production registry.

The immutable coordinate writer validates complete passports before recording
an `X.Y`. Replaying a number requires the same exact passport; another digest
cannot replace it. Minor numbering advances the latest verified line, while
major advancement is an explicit choice. Numeric overflow is refused, and
recording a version preserves the current draft head. Draft-to-version
compilation remains a separate unfinished service.

Component artifacts use the canonical uncompressed ZIP profile. The encoder
preserves existing bytes, including fixed timestamps, Unicode flags and Unix
file modes. The bounded decoder refuses unsafe or colliding paths, extra members,
nonregular files and disagreement between the manifest and actual bytes/modes.
Only the complete canonical archive encoding is accepted: duplicate records,
disagreeing ZIP headers, extra metadata and alternate ordering are refused.
Portable names exclude Windows devices and reserved characters; a file cannot
also be an ancestor of another member, including through a case alias.
Shared directory prefixes must keep one spelling across the archive.
`zip` owns archive decoding; `crc32fast` supplies the wire checksum. Compression
and encryption features are disabled because this format admits neither.

Scope projection archives use the same ZIP transport and retain their own
8,192-member and 64 MiB limits. They preserve explicit empty directories and
declared ordinary Unix permissions. Every file's bytes, length and mode must
match its scope; the complete archive must match the recorded digest and size.
The scope owns whole-path or structured-contribution semantics. Alternate
ordering, undeclared entries and conflicting metadata are refused. Building a
projection does not declare provider support or perform installation.

Native source capture reads explicit files and manifest-bearing directories.
Within Git, it includes tracked and nonignored untracked members without
changing the index; unresolved entries and submodules are refused. Tracked
executable modes survive Windows capture. Filesystem capture refuses links,
credential-named paths, incomplete reads and file/count/depth budgets. A
`hooks.json` capture includes its bounded `hooks/` sibling tree. Adoption owns
registration of the captured source.
Standalone files retain their original artifact bytes and carry their normalized
execute mode separately as `source_mode`; tracked Windows files use the Git
index's mode. Git path selections are literal and do not update the index.

`authoring/contribution` extracts one owned top-level object/table and compiles
it back into a host configuration in memory. JSON, JSONC and TOML retain unowned
settings and comments; JSON number tokens retain their exact precision. Duplicate
keys, scalar contributions and JSON5 extensions are refused. Repeated assembly
is stable. `jsonc-parser` and `toml_edit` own format-preserving syntax; they can
be removed if these native configuration formats cease to be supported. This
service never writes the harness file; that remains the public provider's job.

The native catalog consumes the same passive harness data as other repository
consumers. Declared-layout discovery accepts one explicit scope and root,
including Cursor's distinct configuration root. It reports incomplete evidence
for unsafe links, malformed configuration and exhausted budgets; it never treats
these as an empty inventory. Structural configuration reads return names only.
This service covers catalog layouts; package provenance, recursive portable
discovery and installed-plugin sources remain separate unfinished adapters.

`projection` reads shared provider routes and exact profile identities. It keeps
discovery scope separate from provider target scope, including shared user roots,
configuration-key contributions, translated provider kinds and hook sibling
ownership. A discoverable source can still have no valid provider route. These
facts do not replace live authenticated provider verification before execution.

Headless adoption creates an exact, fifteen-minute plan for one discovered
source. Applying it rechecks content, source bindings and revision heads before
atomically storing bytes, the passport and the verified journal outcome.
Copies retain distinct identities; one vanished matching source can move.
Recapture preserves authored passport fields. Completed replay checks stored
content and never rewinds heads; interrupted expired plans become stale.
The source walk holds directory handles through every layout ancestor. Local
binding paths retain ordinary Windows spelling only after verifying that it
resolves to the same location. Plans preserve exact UTF-8 path bytes separately
from their normalized display; distinct filesystem locations with a colliding
normalized binding address are refused. Identity is supplied by the owning runtime;
this service does not claim cloud authentication or expose authoring commands.

Headless passport editing accepts the embedded closed component-patch shape,
with source, path and secret-field checks. Descriptions use the immutable
version's safe CommonMark profile already at draft entry. The preview deliberately
does not reuse public-profile word moderation, which rejects ordinary technical
descriptions accepted by the version contract; for example, "Kill child processes
after a timeout." This also makes the release format's size, line, link and
image restrictions apply consistently at editing. A plan binds the
owner, exact head, confirmed facts and resulting passport. Applying stores the
revision and verified receipt in one transaction; a failed write rolls both
back. Repeated confirmed values create no revision, and completed replay never
rewinds a newer head. Unchanged facts, visibility and passport extensions remain
intact. These local plans do not publish an object or change its access.

`process` owns one-shot child execution with an absolute executable, explicit
environment, closed stdin, concurrent bounded output and a deadline. Its Git
caller disables fsmonitor, optional locks and inherited Git overrides.
`process-wrap` owns Unix process groups and Windows job objects; the adapter
terminates descendants on exit or refusal. This is lifecycle control, not an
execution sandbox. Its dependency is removable when child execution is removed;
no async runtime or tracing feature is enabled for it.

## Modules and proof

| Owner | Responsibility |
| --- | --- |
| `main.rs` | Process I/O and exit status |
| `lib.rs`, `error.rs` | Invocation and envelope/error boundary |
| `registry.rs` | Executable command definitions and dispatch |
| `canonical.rs`, `digest.rs` | Strict NFC + RFC 8785 data and closed digest domains |
| `config.rs`, `files.rs` | Explicit bounded configuration reads and path rendering |
| `snapshot.rs`, `objects.rs` | Explicit backup inspection and verified local reads |
| `wire.rs`, `passport.rs`, `passport/` | Offline wire validation, immutable passport rules and content identities |
| `http.rs`, `catalog/` | Bounded anonymous catalog reads and explicit public cache |
| `projects/` | Bounded project discovery and content-free file evidence |
| `environment.rs` | Exact setup prerequisites, project binding and variable-name presence |
| `selection/` | Verified exact dependency graphs and deterministic ordering |
| `store/`, `files/owned.rs` | Explicit owned state, atomic revision writes and shared private-file primitives |
| `archive.rs`, `artifacts.rs`, `projection/artifact.rs` | Shared canonical ZIP transport and closed component/scope archives |
| `authoring/source.rs`, `process.rs` | Complete bounded source capture and explicit child process lifecycle |
| `authoring/contribution.rs` | Owned configuration extraction and format-preserving in-memory assembly |
| `harnesses.rs`, `authoring/discovery.rs` | Shared declarative harness facts and bounded inspection of native layouts |
| `projection.rs` | Shared exact provider profiles and target-relative ownership routes |
| `authoring/adoption.rs` | Exact local adoption plans, binding reconciliation and atomic journaled registration |
| `authoring/passports.rs`, `store/journal.rs` | Closed confirmed edits, exact head plans and bound atomic receipts |
| `store/versions.rs` | Verified immutable coordinates, explicit major advancement and replay without draft movement |
| `provenance.rs` | Offline PEP 740 cryptographic verification and publisher policy |

The provenance service accepts a caller-owned trusted root and an artifact
SHA-256. `sigstore-verify` verifies the DSSE signature, certificate chain, SCT,
Rekor inclusion/checkpoint, signed entry timestamp and artifact binding. The
service then enforces the signed source repository, workflow and deployment
environment. It does not treat the unsigned publisher description as evidence.
Trust-root refresh, acquisition and installation are not exposed as commands.
The example's embedded production trust root is for this fixed evidence run;
an online provider lifecycle needs authenticated TUF refresh before C4.

Rust tests cover the existing canonical corpus, executable refusals and
a real PyPI attestation with adversarial mutations. Public fixture source URLs,
the artifact digest and publisher are in `tests/fixtures/provider.json`; no
wheel or secret is stored in the repository. `scripts/verify.py` is a development
oracle: it checks existing Python envelope/help consumers, independently
recomputes the registry digest and creates a real schema-53 backup with a live
WAL. Native children run with an empty PATH and home. CI runs the proof on
Linux, Windows and macOS. The same oracle drives project reads through real
files and catalog reads through TCP using the shared contract corpus, including
safe-Markdown vectors, historical bytes, privacy/digest refusals, offline
provenance, cache corruption, contention and eviction.
Graph evidence uses real component/setup versions and saved proposals, checking
shared dependencies, input-order independence, substitution, deletion, stale
coordinates and depth/edge exhaustion against the existing graph consumer.
The native state journey checks persisted history after reopen, stale writes,
ancestor replay, writer exclusion and rollback before commit. The schema oracle
compares every table, index and constraint with a real schema-53 registry.
Artifact vectors retain exact bytes from the existing encoder and exercise
Unicode names, executable metadata, corrupt content and escaping/undeclared paths.

For an independently downloaded artifact and its provenance, the explicit
evidence runner hashes the actual file before verification:

```sh
cd apps/cli-v2
cargo run --locked --release --example verify-provider -- ARTIFACT PROVENANCE PUBLISHER_JSON
```

`PUBLISHER_JSON` contains `repository`, `workflow` and `environment`. This runner
verifies evidence; it neither trusts the artifact as an installed provider nor
executes it. Dated measurements and oracle differences belong to the checkpoint
issue, not a growing copy of release reports here. The ordered migration plan
remains in the repository roadmap. Add modules only when a working capability
needs them; generate command documentation from the registry rather than
maintaining a second command list.
