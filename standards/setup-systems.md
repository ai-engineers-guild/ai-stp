# setup-systems

The seven `NDDev-OpenNetwork/*-setup-system` providers (claude, codex,
grok, pi, cursor, opencode, antigravity) — Rust binaries rendered from the
private `setup-systems` workspace — and the provider-protocol v3 boundary this
repository consumes. The standard covers what this tree pins, who is allowed
to move which side of the contract, and how a release claim is proven.

## Version contract

- The wire contract is **provider-protocol v3**, carried by the generated
  conformance kit at `provider-kit/v3` (`kit_version` in
  `KIT-IDENTITY.json`; `0.2.13` at the time of writing). The kit is produced
  by `release_scripts/provider_kit.py` and byte-compared by
  `provider_kit.py --check provider-kit/v3` inside `just back-static`.
- Every released kit version's aggregate digest is pinned in
  `tests/golden/provider-kit/identity-ledger.json`. A kit version whose bytes
  moved is the same defect as a republished immutable `X.Y`: the pin fails
  or, worse, keeps matching a name that now means something else.
- Provider releases are consumed as **exact immutable tags**, never a
  floating `latest`. The active tag is recorded with its evidence in
  `docs/operations/provider-integration-state.md`.
- The shipped trust pin is `apps/cli/src/ai_stp_cli/provider/provider-policy.toml`:
  per-repository `build_attestations` (repository + `release.yml` signer
  workflow, `verified_publisher = true`), `supported_protocols = [1, 3]`, and
  empty `releases`/`allowed_*` lists — nothing installs on the signed path
  while those stay empty.
- The harness→repository map is committed in
  `apps/cli/src/ai_stp_cli/provider/attested_bind.py` (`HARNESS_REPOSITORIES`)
  and must equal the policy's `build_attestations`; drift is a test failure,
  not a second map.

## Rules

1. **The kit is generated.** Edit `release_scripts/provider_kit.py` and
   regenerate; never edit `provider-kit/v3` output by hand.
2. **The reader ships first.** A field or operation the strict reader
   validates lands in a released consumer + kit *before* any provider
   declares it. Kit history is the precedent: `0.2.8` opened
   `plan_request_fields` to `end_state`, `0.2.9` to `status_request_fields`,
   `0.2.13` to `instruction_section` — each let a provider declare the name
   without older consumers refusing the whole `provider-info`. The reverse
   order is a two-rollout defect: an older reader cannot be taught tolerance
   after the fact.
3. **Evidence is per-tag.** A conformance count binds to the tag it was
   measured on; `0.0.65` numbers are not evidence for `0.0.73`. When a
   release's evidence is refreshed, the state doc adds a dated row rather
   than rewriting the old one.
4. **"Not measured" is a third status.** An absent host dependency (bubblewrap,
   sandbox-exec, a GitHub token) is reported as unmeasured — never as a pass
   and never as a refusal. A check that passes while its subject is missing
   is green exactly when checking mattered.
5. **No state bleed.** Evidence recipes run against temporary `HOME`/XDG
   state and disposable targets; a run must not touch the owner's live
   harness configuration.

## Accepted and rejected features

Accepted:

- Protocol v3 invocation through `provider/invocation_v3.py` +
  `conformance_v3.py`; protocol 1 kept in `supported_protocols` for the
  declared compatibility line.
- Attested GitHub builds via `build_attestation.py` (pinned `gh attestation`
  flags) and PEP 740 index provenance via `index_attestation.py`.
- Sandboxed provider launch per OS: bubblewrap on Linux, AppContainer on
  Windows, `sandbox-exec` on macOS — each after a native transport probe.
- Vendored kit on the provider side, byte-bound: `setup-systems` owns its
  vendored copy; a divergence is reported, never patched from here.

Rejected:

- Floating provider versions or `latest` resolution — installs bind an exact
  tag + commit + asset digest.
- Widening local policy from a downloaded manifest — the manifest describes
  itself; `provider-policy.toml` describes what this machine believes.
- The displaced signature-only provider line — the shipped policy no longer
  trusts it (see the policy header).
- Hand-editing rendered public trees or kit output.
- Treating a skipped/unavailable evidence cell as a pass.

## Verification

| Mechanism | What it proves |
| --- | --- |
| `release_scripts/provider_kit.py --check provider-kit/v3` (in `just back-static`) | Kit bytes match the generator; ledger digest unchanged |
| `tests/golden/provider-kit/identity-ledger.json` | No released kit version re-published with moved bytes |
| `tests/contract/test_provider_*`, `tests/unit/test_cli_provider_*` (~29 files) | Protocol, conformance, attestation binding, launchers, status envelope |
| `just evidence-providers <tag>` | Released provider bytes answer the contract, per harness |
| `just evidence-software <tag>` | Released providers survive the consumer install/status/update/remove path |
| `just evidence-provider-scopes <setup_systems_root>` | Every provider profile survives a mutating lifecycle on disposable targets |
| `docs/operations/provider-integration-state.md` | The dated public record: active tag, vendored kit digest, measured evidence |
