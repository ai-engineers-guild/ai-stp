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

## Modules and proof

| Owner | Responsibility |
| --- | --- |
| `main.rs` | Process I/O and exit status |
| `lib.rs`, `error.rs` | Invocation and envelope/error boundary |
| `registry.rs` | Executable command definitions and dispatch |
| `canonical.rs`, `digest.rs` | Strict NFC + RFC 8785 data and closed digest domains |
| `config.rs`, `files.rs` | Explicit bounded configuration reads and path rendering |
| `snapshot.rs`, `objects.rs` | Explicit backup inspection and verified local reads |
| `passport.rs` | Embedded schema validation, passport identities and revision digests |
| `provenance.rs` | Offline PEP 740 cryptographic verification and publisher policy |

The provenance service accepts a caller-owned trusted root and an artifact
SHA-256. `sigstore-verify` verifies the DSSE signature, certificate chain, SCT,
Rekor inclusion/checkpoint, signed entry timestamp and artifact binding. The
service then enforces the signed source repository, workflow and deployment
environment. It does not treat the unsigned publisher description as evidence.
Trust-root refresh, acquisition and installation are not exposed as commands.
The example's embedded production trust root is for this fixed evidence run;
an online provider lifecycle needs authenticated TUF refresh before C4.

Three Rust tests cover the existing canonical corpus, executable refusals and
a real PyPI attestation with adversarial mutations. Public fixture source URLs,
the artifact digest and publisher are in `tests/fixtures/provider.json`; no
wheel or secret is stored in the repository. `scripts/verify.py` is a development
oracle: it checks existing Python envelope/help consumers, independently
recomputes the registry digest and creates a real schema-53 backup with a live
WAL. Native children run with an empty PATH and home. CI runs the proof on
Linux, Windows and macOS.

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
