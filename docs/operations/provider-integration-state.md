---
description: "Public compatibility snapshot for seven provider systems and ai_stp."
last_verified: "2026-09-04"
---

# Provider integration state

Pins belong to provider policy/manifests; the normative wire boundary is
`docs/contracts/provider-protocol.md`. This page lists publicly verifiable
release, capability, and evidence facts.

## Active release

The active public tag for the seven `NDDev-OpenNetwork/*-setup-system`
repositories is `0.0.65`. Each GitHub Release contains seven assets (six native
binaries and `SHA256SUMS`), read back from GitHub. The consumer kit identity
vendored into those trees is `0.2.9`
(`sha256:8abeee1e3469b84b57492ad7d73d794416bca439e381becc0d36ea703bded33b`).

## Capabilities

- Core configuration binary/provider-info exists on six OS/architecture lines
  for all seven systems.
- Software install/update/remove is declared for all seven systems.
- Claude Code, Codex, Grok Build, OpenCode, and Pi declare complete launch;
  Cursor and Antigravity do not.
- Provider-kit `0.2.7` publishes a closed status-response schema; the consumer
  validates the complete envelope at the single invocation boundary.
- Provider-kit `0.2.8` opens `plan_request_fields` to `end_state` (`#54`).
- Provider-kit `0.2.9` opens `provider-info` to `status_request_fields`, with
  `target_scope` as its only member: `status --target-scope <scope>` lets a
  provider digest an unmanaged workspace the way its workspace plan does.
  Accepted by the consumer first, published by the kit, then declared by a
  provider — the `ADR-0125` order, because `provider-info` is compared by exact
  membership. All seven `0.0.65` providers declare `plan_request_fields`
  `{target_scope, end_state}` and `status_request_fields` `{target_scope}`.

## Evidence

On linux/x86_64, `provider conformance --protocol-version 3` against the
attested `0.0.65` bytes reports seven `conforms: true` (Antigravity 46,
Claude Code 44, Codex 60, Cursor 62, Grok Build 44, OpenCode 44, Pi 43).

Exact-current provider plan/digest/apply/update/rollback operations passed 6/6
for all seven systems. The Pi oracle compares pre/post launch output because
both exact vendor releases return `0.0.0` for `--version` on Windows.

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
