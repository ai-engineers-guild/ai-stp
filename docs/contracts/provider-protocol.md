---
description: "Commands, execution boundary, and state mapping of a public provider."
last_verified: "2026-09-01"
---

# Provider protocol

The requirements owner is `SPEC-008`. This document defines the machine boundary: the command set, invocation rules, and state mapping.

## Frozen required v1/v2 commands

```text
provider-info
software-status
software-plan
software-install
software-update
software-remove
validate-bundle
plan-bundle
apply-bundle
status
restore
launch
```

`provider-info` reports the protocol version, harness identifier, provider version, supported actions, bundle formats, systems, architectures, and limits. A closed check compares this response with the actions actually available in the CLI.

## Execution boundary

A command receives an argument array and uses `shell=false`, an explicit absolute target directory, the exact executable, a filtered environment, a timeout, and an output-size limit.

The exact provider artifact is checked before invocation: the path must resolve to
a regular file with execute permission on the current host. An existing but
non-executable file returns `AI_STP_DEPENDENCY_UNAVAILABLE`, not an internal process error.

The output-size limit constrains what is **read**, not what is retained. The caller
reads no more than the limit and stops a provider that exceeds it; such a response
is not parsed and is treated as a failure. A limit applied after reading to EOF
limits nothing: it leaves the caller's memory at the disposal of another program.

A filtered environment is a list of permitted names with their actual values,
not the same names cleared. A provider cannot start without `PATH`, and that
failure would appear to be a provider defect rather than a caller defect.

Read commands create no state. `validate-bundle` and `plan-bundle` do not modify the target. `apply-bundle` accepts the exact plan hash, acquires a lock, and revalidates the target after locking.

## Exact HarnessBundle transfer

The three bundle commands receive the same immutable binding after the common
protocol arguments `--target` and, for v2, `--phase`:

```text
--bundle <absolute-content-addressed-path>
--bundle-format ai-stp-bundle/1
--bundle-digest sha256:<logical>
--artifact-digest sha256:<raw-zip-bytes>
--bundle-size <decimal-bytes>
```

`plan-bundle` adds `--expected-target-digest <digest>`. `apply-bundle` receives
the same argument and `--plan-digest <provider-plan-digest>`. The order above is
part of the argv contract; the path identifies a regular file, not a directory
or link. The path is not part of identity and is not stored in the plan: identity
is defined by the format, two digests, and size.

The provider response echoes `bundle_format`, `bundle_digest`, `artifact_digest`,
and numeric `bundle_size`. `validate-bundle` additionally returns `valid=true`.
`plan-bundle` returns `state=planned`, canonical SHA-256 `plan_digest`, the same
`expected_target_digest`, and a nonempty list of `effects` strings. `apply-bundle`
returns its own state, the same target digest, and exact `plan_digest`.
Command-specific additional fields such as `backup_ref` are allowed but do not
replace the required echoes.

### What `target_digest` covers

The digest is computed **over managed paths, not over the directory** containing
them: roots from the provider's `native_namespaces` are traversed, while its own
control directory and entries it does not own are excluded.

This is not a cosmetic clarification. If read as "over the entire target" under
`user_root`, any neighboring product entry created between plan and apply is
indistinguishable from drift, and the operation fails at a root intentionally
shared by four products. The more successful the convention, the more frequent
the failures. When read as "over managed paths," another product's `skills` do
not enter the digest, and the scopes retain the same meaning.

Before traversal, the declared set is reduced to its **coverage**: a namespace
nested under another declared namespace is visited once. Otherwise identity
would depend on how the declaration is phrased; during the transition window,
both parent and child are declared (`plugins` and `plugins/local` for cursor,
`antigravity-cli/plugins` and `config/plugins` for antigravity), and child bytes
must not be hashed twice.

This was recorded after discovering that the word appeared only in statements
about what the digest *proves*, never in a sentence about what it *covers*. The
implementation happened to be correct; coincidence is not a contract.

After acquiring its own target lock, the provider returns `stale` without
performing an effect if the target digest already differs from
`expected_target_digest`. The consumer records this as terminal `stale`, not
`partial`: an exact response with required echoes proves refusal before effect.
A response error or echo mismatch after invocation still means `partial`, because
absence of an effect is then unproven.

The consumer checks echoes before recording the result. A validation or plan
mismatch blocks operation-plan creation. A mismatch after apply invocation means
`partial`, because lack of a verifiable response does not prove lack of effect.
Before apply, the consumer rechecks raw SHA-256 and cached-byte size; a missing or
corrupt artifact blocks invocation. Observe-only `resume` calls only
`provider-info` and `status` and never repeats `apply-bundle`.

## Managed-path diagnostics

The installation plan shows relative `managed_paths` from the exact stored
HarnessBundle. On `local_drift`, `target diff` compares them with the
`provider_target` of the last verified operation and returns `managed_detail`:
`available`, `unavailable`, or `not_applicable`. Available detail contains
`managed_changes` with stable codes `modified`, `added`, and `deleted`, a
relative path, and SHA-256 evidence; an unsafe link is marked
`observed_digest=unsafe`.

Inspection is limited to managed roots, does not follow symbolic links, does not
show an absolute local path, and does not modify the target. Loss of the exact
bundle, target binding, or verified history is not guessed from the current
directory and instead fails closed with `unavailable`. The result is evidence for the
user and plan; it does not automatically start recovery or cleanup.

## Network and boundary version

Frozen protocol v1 declares no network requirement and establishes no process
network isolation. The absence of network fields in `Boundary` and successful
command execution do not prove network denial. Therefore v1 cannot serve as
evidence for the network class of hostile corpus `#184`.

Network capability is introduced only by protocol v2 under
`ADR-0047-provider-network-capability.md`. Each action declares
`network_requirement` as `none`, `artifact_download`, or `runtime_external`, and
the result reports `network_enforcement` as `enforced`, `unavailable`, or
`not_requested`. With requirement `none`, absence of a proven isolation mechanism
means a typed refusal before invocation. An unknown protocol version is not parsed
optimistically, and v1 is not extended with additional fields.

The closed command/phase matrix, wire schema, and v2 pre-invocation decision live
in `ai_stp_cli.provider.protocol_v2`. `software-install` and `software-update`
have separate `download` and `apply` phases: the first declares
`artifact_download`, the second `none`. A model is not presented as a network
sandbox: without a proven launcher on the current OS it returns `unavailable`
and does not close `#184`.

Every v2 invocation passes required arguments `--phase <phase>` and
`--target <absolute-directory>`. A missing or unknown phase is not guessed. Before
the first `provider-info`, the version is selected by a verified release manifest
or an explicit consumer conformance invocation, so an unverified process response
cannot switch the boundary from v1 to v2 itself. The consumer adds observed
`network_enforcement` beside the provider payload; a value in the payload itself
is not evidence. `provider conformance --protocol-version 2` checks the exact v2
declaration, the closed matrix for every command/phase pair, the consumer decision,
the shared hostile corpus, states, and repeatability of reads. Without the argument,
it preserves frozen v1 behavior.

Conformance passes temporary literal ZIP artifacts, not JSON stubs, under the same
exact argv contract as installation. A valid bundle must pass validation and a
side-effect-free plan with exact echoes. Every hostile case receives separate
content-addressed bytes: paths, duplication, link/special metadata, a limit,
unknown surface, mismatched digest, or unsupported version. The corpus is deleted
after the run. Conformance does not invoke `software-install/update/remove`,
`apply-bundle`, `restore`, or `launch` on the user-supplied target: evidence for
those actions belongs to provider E2E with a disposable target and confirmed plan.

A separate Bubblewrap launcher is implemented for Linux. Capability becomes
`enforced` only after positive control proves local IPv4, IPv6, and DNS-UDP
endpoints reachable outside and the same transports blocked inside a new network
namespace. The exact `bwrap` path, version, and SHA-256 are checked; a group/world-
writable or non-root-owned executable/ancestor is rejected. `provider network --json`
applies the closed v2 decision and reports capability; with `unavailable`, local
v2 actions are unavailable. The launcher wraps exact provider argv through
`ai_stp_cli.provider.invocation_v2`; the permitted download phase runs without a
network namespace, while apply again requires the proven launcher. `install plan`
selects the version before the first invocation and stores it and the absolute
provider target in the immutable plan; `apply` and `resume` use only that approved
version. Thus the v2 lifecycle uses the same phase invoker and cannot be downgraded
by an argument after confirmation. Real provider releases remain release blockers.
Under `ADR-0062`, the current required profile is Linux x86_64; macOS without a
separate launcher/run has `not_verified`, fails closed for `none`, and does not
block the current release.

**Protocol v3 on a platform without a launcher.** Windows and macOS provide no
ordinary CLI mechanism that denies network access: bubblewrap is Linux-only;
AppContainer denies network but cannot reach an arbitrary target without changing
parent ACLs; `CreateProcessInSandbox` and Windows Sandbox are unavailable or a
separate component. Therefore the v3 local phase runs there **without isolation**:
deliberate debt under `ADR-0126`, allowed for exactly two reasons: a trusted
release or explicit `--unverified-provider`. The rule is about whose executable
runs, not about whether the command writes: `target status`, `target diff` and
`target backups` establish the same two signals — a named `--provider-manifest`,
the operator's `--unverified-provider`, or the release the pair was last
verified under when the named executable is its exact bytes, read from the
journal without re-running the build attestation. Protocol v2 receives no
exception by construction and refuses before invocation.

`network_enforcement` **never** becomes `enforced` in this case, or the sole
output by which the debt is found would hide it. `provider network --json`
names the debt in a separate `v3_local_phase` field:

- `network_denied` — the launcher is proven and the phase runs inside it;
- `unisolated_by_trust` — no launcher exists on this platform, the phase runs
  with reachable network, and `v3_local_phase_reasons` lists reasons, one of
  which the caller must provide;
- `refused` — a launcher is possible here but absent, so nothing runs.

The last two are intentionally distinct: absent `bwrap` on Linux is a missing
dependency, while absent mechanism on Windows is a missing OS capability, and
`unisolated_local_phase` refuses to construct on a platform capable of isolation.

The debt boundary is measurable and measured. All seven released `0.0.6`
providers import no network symbols (`socket`, `connect`, `getaddrinfo`, `inet_*`,
and others are absent), link only to `libc` and `libgcc_s`, and a traced local-
phase run yields zero `socket` and zero `connect` calls for each. This is an
artifact property, not isolation: `syscall` and `execvp` are imported, and a
process not linked to networking can still spawn a linked child. A namespace
covers the entire process tree; import inspection covers one process. It reduces
the debt but does not eliminate it.

## Capability-negotiated protocol v3

Protocol v3, adopted by `ADR-0061-capability-negotiated-provider-protocol-v3.md`,
does not change v1/v2. It separates the required wire boundary from native
product capabilities and has closed command and operation sets.

These sets have one owner: `provider-kit/v3/manifest.json`, generated from
`apps/cli/src/ai_stp_cli/provider/protocol_v3.py`. The exact revision is named by
`provider-kit/v3/KIT-IDENTITY.json` (`ADR-0085`). The list is intentionally absent
here: a vocabulary recorded in prose in a second location drifts from the
executable source, discovered only after someone implements the prose.

`provider-kit/v3/provider-info.schema.json` declares
`$id: https://nddev.asia/schemas/provider-protocol/v3/provider-info.json`. Under
In JSON Schema 2020-12 this is an **identifier** defining the base URI. The same
bytes shipped in the kit are served at that address: an external validator that
follows it receives the schema, not a 404. Implementations still verify the kit
locally against `SHA256SUMS`; the network response does not replace
`KIT-IDENTITY.json`.

Only what the machine file cannot express follows: the meaning of the divisions.

Commands are divided into a shared setup/bundle core and optional commands.
`launch` is optional and allowed only with a declared capability; its absence
from the parser of a provider without launch ownership is correct conformance.

Operations are divided likewise. Core operations cover materialization,
replacement, backup, restoration, and removal of a provider-owned setup
projection; optional operations cover the provider-owned program lifecycle and
runtime launch through the native boundary.

Claude Code correctly conforms to core without software/launch ownership. Codex
and Pi may declare software install/update and launch without software remove.
The consumer does not invoke an undeclared operation. An unknown operation,
component, native surface, format, protocol, projection profile, OS, or
architecture is rejected with a stable reason code before plan and target
mutation. A permission profile absent from closed `permission_profiles` is
neither `unsupported_operation` nor `projection_profile_mismatch`.

`provider-info` returns a build-manifest digest and content-addressed projection
profile: component/projection kinds, native identifier namespaces, bundle
formats, limits, permission profiles, OS, and architectures. The setup compiler
builds a projection only for the exact profile, and the provider independently
validates the bundle. The permission profile is a separate plan input and is not
part of the setup/component digest.

For `ai-stp-bundle/2`, the provider resolves the profile before bundle
validation and compares its ID, digest and scope with `bundle.json`'s
`projection_profile`. It then validates every `component_adaptations` entry and
owner/path closure before returning a provider plan. A profile advertising only
`ai-stp-bundle/1` cannot accept `/2`, and a `/2` bundle cannot borrow a different
scope profile even when its final paths happen to pass the provider allowlist.

The `provider-info` field set is closed and compared for exact equality, so an
unknown field rejects the entire response, not part of it. The only optional name
is `scoped_projection_profiles`: an array of profiles, each declaring
`target_scope` from `global` / `project`. An entry with `global` is rejected
because `projection_profile` declares global scope; array scopes are unique; each
entry's digest binds its declaration together with its scope. Absence of the
array means ownership of global scope only and is not degradation.
`projection_profile` is changed by no field, so the declaration and digest of a
release predating this extension remain unchanged. Scope is resolved once, by
planning time when the target is known; the plan artifact and status still carry
one `projection_profile_digest`, the resolved profile's digest. The decision and
release order are in `ADR-0125`.

The optional program lifecycle (`software_install`, `software_update`,
`software_remove`) adds no commands: the same `plan-operation` and
`apply-operation`, journal, backup, and plan-digest apply. The provider opens no
socket. `plan` returns exact artifact identity offline; the network-owning party
fetches those bytes; `apply` checks digest and length against the plan and
extracts offline. A provider that did not declare these operations does not plan them.

`--target` is the configuration directory. `--prefix` is the program directory.
They are different absolute paths with different lifetimes. If
`--software-version` is omitted, the pinned version is used; if passed, exactly
that version is required or the operation is refused. An unpinned platform
refuses with `unsupported_platform`.

The plan carries a `software_artifacts` array. One element means one file;
multiple elements mean multiple files, in the same order in which `apply`
receives repeated `--software-artifact` flags. Element fields are `platform`,
`url`, `sha256`, `byte_length`, and `entry_point`. A directory at apply does not
hide which file corresponds to which plan record. `software_remove` is plan and
apply without download and without `--software-artifact`.

`apply-operation` remains in `forbidden_in_safe_conformance`. Purity of `plan`
for a declared program lifecycle is checked: a provider that declares an
operation but cannot identify the artifact offline is precisely the failure this
contract must catch.

`plan-operation` is always pure. It binds a stable operation ID, operation,
canonical target and snapshot, provider build, consumer-verified release hash and
protocol, exact identities of an optional bundle and optional `BackupRef`,
permission profile, platform/runtime identity, expiry, and effects.
`apply-operation` receives the canonical plan artifact and exact digest, locks the
target, and rechecks preconditions after locking. A success response carries
`state`, the same `plan_digest`, and `expected_target_digest`; the four bundle
echoes remain on `validate-bundle` and `plan-operation`. A typed refusal after
lock is `state=refused` with `reason=stale` (no effect) or `state=stale`. A
mismatched or expired plan has no effect. A timeout/malformed response after a
possible effect yields `partial` without automatic retry. After install, `status`
proves `state=managed`, `target_digest`, protocol/provider identity, and drift
`clean` or `verified`; nested `provider_state` is allowed.

Before the first write, the provider publishes a target-local durable journal in
phase `prepared`, bound to the exact plan digest, operation ID, and target-bound
`BackupRef`. After result verification, the journal transitions atomically to
`committed`; cleanup occurs only after durable state. Presence of a journal,
transaction directory, or incomplete backup slot makes `plan-operation` purely
refuse with `recovery_required`. The only command authorized to resolve this state
is `recover-operation`: `prepared` restores the exact pre-operation target;
`committed` only verifies the exact result and cleans up remnants. `resume` may
invoke this command after read-only `status`, but never repeats `apply-operation`.

After finalization, a prepared exact graph and a composed graph form one immutable
setup, `SetupDefinition`, and pass through the same HarnessBundle, plan,
confirmation, apply, state paths, backup, recovery, and removal. Channel/marketplace
are acquisition or projection metadata, not setup identity.

Provider state binds protocol/release/harness/target, the SetupVersion passport and
SetupDefinition, ordered exact components, logical bundle/raw artifact,
projection-profile/provider-plan, operation/precondition, native ownership,
`BackupRef`, previous verified identity, and drift state. Secret values are
prohibited. `status` does not migrate an old stamp; mutation first creates a
backup, then atomically writes the new schema.

A conversion record binds component kind, native surface, and projection kind.
Every exact component must own at least one manifest-bound native file. Before
plan, the provider rechecks product grammar (for example JSON/TOML) and required
full-tree markers (`SKILL.md`, `plugin.json`, `package.json`); silent directory
truncation and an empty projection are prohibited.

The release digest does not come from `provider-info`, which would create an
artifact self-reference. The consumer verifies the exact executable/release
before invocation, passes its digest into the plan, and checks it against the
immutable operation; the provider reports an independent build-manifest hash.

The machine declaration and closed wire schema belong to
`ai_stp_cli.provider.protocol_v3`. The public conformance kit is distributed
separately from the private control plane and contains exact schemas, examples,
hostile corpus, and expected digests; a public provider's runtime dependency on
a private repository is prohibited.

## Read-only observation

`target status`, `target diff`, and `target backups` reach a provider only when
the caller names one with `--provider`. These reads carry no release manifest
to select the protocol from: an explicit `--protocol-version` wins, and without
it the observation speaks protocol v3 — the protocol released providers
actually speak. The former fallback to frozen v1 produced a conversation that
succeeded while carrying no target identity, so drift went unreported exactly
where the command exists to report it.

A named provider whose status answer carries no target identity is reported as
an envelope warning rather than rendered as a clean pair: the journal half of
the survey is still answered, and the missing live half is stated instead of
implied.

## Observing external authorization

The exact selected `SetupVersionPassport` declares the
`requires_authorization` requirement. Only the provider owns the native target
and can observe whether the corresponding configuration is complete. Therefore
a `status` response may contain optional command-specific evidence:

```json
{
  "authorization": {
    "kind": "external_service",
    "state": "pending"
  }
}
```

Closed `kind` values are `user_account` and `external_service`; closed `state`
values are `pending` and `ready`. The field contains no user identifier, login
address, token, or other secret. Its absence preserves protocol v1 compatibility
but does not prove readiness: the passport-declared requirement remains
`needs_configuration`. Only a matching `kind` with `state=ready` clears the wait;
an unknown form or mismatch fails closed with a typed refusal. The full rationale
is recorded in `ADR-0052-provider-observed-authorization-readiness.md`.

`install plan` shows declared `required_authorization` before target mutation. A
successful apply does not substitute for readiness: after configuration, the
agent invokes `target status` with the same exact provider and explains the
remaining requirement from machine output rather than guessing from a local flag
or secret presence.

## State mapping

The provider and `ai_stp` maintain their own journals. A provider result maps unambiguously to a durable operation under `contracts/operation.md`:

| Provider state | `ai_stp` operation state |
|---|---|
| `planned` | `planned` |
| `applying` | `applying` |
| `applied_unverified` | `applied_unverified` |
| `verified` | `verified` |
| `partial` | `partial` |
| `failed` | `failed` |
| `stale` | `stale` |
| `rolled_back` | `rolled_back` |

The `approved` and `cancelled` states belong only to the `ai_stp` operation and have no provider source. An applied but unverified state is not called success.

## Bundle

The external bundle conforms to `harness-bundle.md`. The provider rejects an unsupported version, directory escape, links, special devices, path conflicts, exceeded limits, an unknown native surface, and a hash mismatch.

## Backup and partial failure

A backup is created before the first mutation; the bytes belong to the provider, and `ai_stp` stores the exact reference. A new setup is installed into an inactive target; the next-launch pointer changes after state and launch-readiness verification.

A timeout after a possible effect, recovery failure, and unknown state return `partial` with the last confirmed state. Retrying without a separate recovery check is prohibited.
