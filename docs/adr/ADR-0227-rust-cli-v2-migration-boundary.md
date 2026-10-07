---
description: "Develop the Rust CLI against explicit business and compatibility boundaries, with isolated previews and one verified default-runtime cutover."
last_verified: "2026-10-07"
---

# ADR-0227: Rust CLI v2 migration boundary

Status: accepted for development. No Rust CLI runtime ships at this checkpoint.

## Context

The owner now authorizes a clean Rust implementation, `ai-stp-cli-v2`, and asks
for business scope and checkpoints before translation. This supersedes the
earlier deferral in [#57](https://github.com/ai-engineers-guild/ai-stp/issues/57).
The shipped CLI remains Python 0.0.43. Its 245 registered commands, nine task
intents, local schema 53, provider v3 integration and desktop consumer make a
replacement wider than a parser or executable rewrite.

The [frozen baseline](../engineering/cli-v2-scope.md) records implemented
capabilities. Existing Python packaging and update decisions continue to govern
the shipped runtime until a verified native replacement exists. This ADR
authorizes the migration architecture; it does not declare parity or rewrite
active specifications ahead of code (ADR-0194).

## Options

1. Translate Python modules and their unit tests one for one. This preserves
   incidental structure and duplicated orchestration without proving the
   business contract. Rejected.
2. Replace `ai-stp` immediately with a partial Rust CLI that dispatches missing
   commands back to Python. This creates mixed state ownership, ambiguous
   recovery and a misleading native-runtime claim. Rejected.
3. Develop a separate native implementation in complete vertical slices,
   reconcile every shipped capability, then perform one controlled default
   cutover. Chosen. Preview users see only implemented capabilities and use
   separate state; production keeps a complete supported engine throughout.

## Decision

### Implementation and authority

- The future source owner is `apps/cli-v2`, with package name `ai-stp-cli-v2`
  and preview executable `ai-stp-v2`. Create it with the first functioning
  slice, not an empty scaffold. The eventual public executable remains
  `ai-stp`; the product name does not change envelope or API schema versions.
- Start with one Rust package: a headless library and a thin CLI binary.
  Organize modules by business capability. Task and expert adapters call the
  same application services in process. Introduce another crate only for an
  evidenced ownership or dependency boundary, not one crate per Python package
  or command family. Keep desktop's existing build independent.
- One executable registry owns parsing, descriptors, help and capability
  reporting. Register only implemented commands. A task intent is advertised
  only when its advertised flow can reach a verified terminal result or a
  precise refusal/recovery state. A frozen v1 ledger is never the v2 registry.
- Preserve envelope v1, `/v1`, provider protocol v3 and canonical identities
  unless a separate evidenced behavior change updates their actual owners.
  No automatic Python business-logic fallback, model interface, new component
  kind, extension framework or persistent daemon is introduced by this decision.
- Public providers remain the sole native harness writers. Desktop remains a
  process-contract consumer under ADR-0222, even though both programs use Rust;
  it does not link the new domain library as a second engine.

### Compatibility and native dependencies

- The command ledger starts with `retain` for every shipped leaf. Internal
  simplification is encouraged; removing, merging or changing an observable
  operation requires a recorded reason, consumer impact and replacement or
  retirement evidence. Task coverage labels alone do not justify deletion.
- Port project canonicalization, domain-separated hashes, validation and
  exact-version semantics before relying on Rust-generated identities. Test
  existing cross-language vectors; JSON key sorting alone is insufficient.
- Prove native verification of the current provider channel early. The current
  PyPI path uses a CLI-managed Python verifier. A Rust executable that still
  needs that verifier has not met the complete native-runtime goal. Preserve
  exact artifact, publisher, workflow and environment policy; a hash check or
  parsed attestation is not cryptographic verification. Do not implement new
  cryptography or silently change the default channel to resolve this gap.
  Insufficient native verifier evidence blocks cutover and requires a revised
  dependency decision, rather than a weakened trust rule.
- Rust ports of contracts belong to their executable boundary. Python packages
  still consumed by API/worker remain supported; rewriting the backend is not
  part of this migration. Existing Corporate CLI adapters remain in the
  compatibility ledger without expanding or rewriting Corporate policy.

### State, concurrency and rollback

- Previews use an explicit separate state root and temporary harness targets.
  They do not auto-open production `registry.sqlite`, reuse production device
  ownership or silently adopt active installations. Read compatibility starts
  with a verified SQLite backup snapshot, not a raw copy of a WAL database.
- Preserve schema 53 semantics initially. Do not combine the language port
  with a new database design. Define the supported source-version window and
  prove migration from it; refuse newer unknown schemas. The final transition
  covers SQLite, journals, object files, backup references and credential-store
  ownership together, without exporting secrets into migration receipts.
- Before default cutover, quiesce legacy work, check the exact state generation,
  make and verify the backup, and transfer writer ownership atomically. Legacy
  binaries need an effective refusal/ownership guard before v2 can become the
  writer; a guard understood only by v2 does not protect against an old v1.
  No two active production engines write the same state.
- A pre-cutover snapshot proves rollback only before later mutations. After
  v2 changes harness or registry state, a binary rollback is allowed only when
  the old engine can read the latest state and recovery journals. Otherwise
  use a tested reverse conversion or forward repair. Never restore an old
  database over newer harness state and discard intervening operations.
- Installation and update respect the owning installer. A native updater must
  not overwrite a `uv`, system-package or desktop-owned executable. Stage and
  verify replacement outside the active prefix, bind the effect to a digest,
  preserve recovery, and handle locked executables on Windows. An active
  target still changes by durable handoff and restart (ADR-0150).

### Proof and performance

- Keep the new proof set small and organized around risk: canonical contract
  vectors, real SQLite/filesystem scenarios, provider process boundaries,
  interruption/recovery, and a few complete business journeys. Reuse fixture
  corpora and actual API services. Do not port thousands of implementation-shaped
  tests or impose a test-count/coverage quota. Existing required gates remain
  effective until replacement evidence covers their responsibility.
- Measure fresh release-build processes on comparable hosts, separating CLI
  CPU/startup from provider and network latency. Record binary size, peak RSS,
  output correctness and packaged execution. No speed claim comes from debug
  builds, reduced functionality or a daemon hiding startup work.
- `version`, static help and capability metadata must have a direct offline
  path in v2 without credential migration, provider probing or opportunistic
  network housekeeping. Preserve required heartbeat/usage policy through an
  explicit bounded lifecycle design when that adapter is implemented; do not
  accidentally remove delivery while optimizing a read.
- Each completed slice updates its active spec from the implemented behavior,
  regenerates affected contracts and records exact-SHA evidence.

## Consequences

There are temporarily two source implementations, but only one production
writer. Preview distribution, state separation and capability honesty are
required work, not optional documentation. Native provenance, credential access,
installer ownership and rollback are first-class migration risks.

The final switch retires the Python CLI only after all ledger rows have verified
dispositions and the required packaged platform/desktop checks pass. Python
server code and shared packages with other consumers are not removed merely
because the CLI no longer imports them. Historical releases remain immutable.

## Revisit conditions

Revisit this decision when a native attestation verifier cannot preserve the
current policy, a supported state version cannot migrate safely, a contract
consumer needs an incompatible change, or measured evidence requires a package
split. Record the concrete failing boundary and an alternative before expanding
scope. A missed checkpoint does not authorize a Python fallback, a silent
feature omission or a weaker trust line.
