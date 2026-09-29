---
description: "Public compatibility snapshot for seven provider systems and ai_stp."
last_verified: "2026-09-29"
---

# Provider integration state

Pins belong to provider policy/manifests; the normative wire boundary is
`docs/contracts/provider-protocol.md`. This page lists publicly verifiable
release, capability, and evidence facts.

## Active release

The active public tag for the seven `NDDev-OpenNetwork/*-setup-system`
repositories is `0.0.84` (published 2026-09-29 UTC; a vendor pin refresh —
claude 2.1.285, codex 0.159.1, grok 1.0.45, pi 0.99.1, cursor
2026.09.28-64d2043, antigravity 1.2.13; opencode 1.18.33 unchanged). Pi's
standalone archive retired its `0.0.0` `--version` placeholder and now prints
its release version. `0.0.83` (second audit wave) and `0.0.82` (eight-tree
prose audit) were published 2026-09-29. The vendored consumer
kit is unchanged at `0.2.15`
(`sha256:094886dd93108ee823350262d332ddd1b02044fdfb835fb055bde91668ab9ebb`),
byte-identical to `provider-kit/v3/` in this repository — verified by a
recursive diff of the two trees on 2026-09-29 — and matches
`provider-kit/v3/KIT-IDENTITY.json` and
`tests/golden/provider-kit/identity-ledger.json`.
`0.0.81`/`0.0.80` (2026-09-29), `0.0.79` (2026-09-28) and `0.0.74`
(2026-09-24) remain prior public tags; they are not the current release.

Antigravity's non-minimal provider setups retain the historical access key and
add `allowNonWorkspaceAccess`. A fresh native Antigravity CLI 1.2.10 process on
Linux read the new key as enabled; the historical key alone read disabled.
Software artifact pins and the provider wire boundary did not change.

## Capabilities

- Core configuration binary/provider-info exists on six OS/architecture lines
  for all seven systems.
- Software install/update/remove is declared for all seven systems.
- All seven systems declare `launch`: five bind the documented config-home
  variable, Cursor launches under a copied process home because its product
  resolves those surfaces from `HOME` itself, and Antigravity launches only
  against the documented `~/.gemini` home.
- Provider-kit `0.2.7` publishes a closed status-response schema; the consumer
  validates the complete envelope at the single invocation boundary.
- Provider-kit `0.2.8` opens `plan_request_fields` to `end_state` (`#54`).
- Provider-kit `0.2.9` opens `provider-info` to `status_request_fields`, with
  `target_scope` as its only member: `status --target-scope <scope>` lets a
  provider digest an unmanaged workspace the way its workspace plan does.
  Accepted by the consumer first, published by the kit, then declared by a
  provider — the `ADR-0125` order, because `provider-info` is compared by exact
  membership. All seven `0.0.65` providers declared `plan_request_fields`
  `{target_scope, end_state}` and `status_request_fields` `{target_scope}`.
  Kit `0.2.13` additionally accepts `instruction_section` and the optional
  `patch_instruction_region` operation; a bound provider that does not
  declare that operation leaves `initialize` blocked.

## Evidence

On 2026-09-29 (UTC), the `0.0.84` publish readback ran the released
`ai-stp-cli` in an isolated container under enforced network isolation:
`exact=7 refused=0 unmeasured=0` — every provider auto-acquired as
`verified_publisher` and returned `conforms` on protocol-v3 conformance
(Antigravity 46, Claude Code 44, Codex 60, Cursor 62, Grok Build 44,
OpenCode 44, Pi 43 cases). The same readback legs ran for `0.0.82` and
`0.0.83`. Conformance was not re-run against `0.0.80` or `0.0.81`; the
`0.0.79` readback below was the last pass measured before the readback leg
carried the consumer check.

On 2026-09-28 (UTC), the released `ai-stp-cli` 0.0.33 auto-acquired attested
`0.0.79` providers through the publish readback: `exact=7 refused=0
unmeasured=0` — all seven resolved as `verified_publisher` and ran
protocol-v3 conformance under enforced network isolation in temporary
HOME/XDG state. The same readback found seven release assets per provider,
six platform wheels on PyPI, and a non-yanked crates.io version for every
provider. These are provider-contract checks, not native coding-agent
qualification on every platform.

Historical: on 2026-09-25 (Asia/Almaty), the released `ai-stp-cli` 0.0.28 automatically
acquired attested `0.0.74` providers and ran protocol-v3 conformance on
linux/x86_64 with network isolation required. All seven returned
`conforms: true`: Antigravity 46, Claude Code 44, Codex 60, Cursor 62,
Grok Build 44, OpenCode 44, and Pi 43 cases. The first pass acquired the
previous release for Claude Code and Grok Build during publication propagation;
those two were repeated after the new wheels appeared in the simple index.
The earlier version mismatches remain separate failed observations.

Historical: for `0.0.74`, registry readback found six platform wheels on PyPI
and a non-yanked crates.io version for every provider. The publish workflow
checked GitHub assets before the tag-triggered builds completed and failed
that early readback. A prior runner could not provide network isolation and
reported `NOT MEASURED`; the local conformance run above supplies that missing
measurement without weakening the isolation requirement.

Historical: conformance was not re-run against `0.0.73`. Historical
linux/x86_64 counts against attested `0.0.65` bytes were seven
`conforms: true` (Antigravity 46, Claude Code 44, Codex 60, Cursor 62,
Grok Build 44, OpenCode 44, Pi 43). Those numbers are not evidence for
`0.0.73`.

Historical: plan/digest/apply/update/rollback operations passed 6/6 for all
seven systems against the `0.0.65` line. The Pi oracle compares pre/post
launch output because both exact vendor releases return `0.0.0` for
`--version` on Windows. That 6/6 count was not re-run against `0.0.73`.

All three operating systems deny network access by device: Linux uses
Bubblewrap, Windows AppContainer, and macOS the system `sandbox-exec` after a
native transport probe. Without an executable or proof, the local phase fails
closed; there is no trust exception.

The filesystem boundary is the same on all three: writable only at the target
and explicitly named caller paths.

Provider implementation/release and consumer enforcement are separate commits
and change boundaries. The consumer status-response enforcement schema is
complete, and cross-repository consumer evidence now exists on both subjects:
`evidence-software` for the program lifecycle and `evidence-config` for the
configuration lifecycle, seven rows each, plus `evidence-contribution` for the
three native MCP forms.
