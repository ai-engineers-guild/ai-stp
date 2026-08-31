---
description: "Public compatibility snapshot for seven provider systems and ai_stp."
last_verified: "2026-08-31"
---

# Provider integration state

Pins belong to provider policy/manifests; the normative wire boundary is
`docs/contracts/provider-protocol.md`. This page lists publicly verifiable
release, capability, and evidence facts.

## Active release

The active public tag for the seven `NDDev-OpenNetwork/*-setup-system`
repositories is `0.0.48`. Each release contains six native binaries and
`SHA256SUMS`, read back from GitHub.

## Capabilities

- Core configuration binary/provider-info exists on six OS/architecture lines
  for all seven systems.
- Software install/update/remove is available 6/6 for all seven systems.
- Claude Code, Codex, Grok Build, OpenCode, and Pi declare complete launch;
  Cursor and Antigravity do not.
- Provider-kit `0.2.7` publishes a closed status-response schema; the consumer
  validates the complete envelope at the single invocation boundary.

## Evidence

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
complete; the next step is cross-repository evidence on the consumer path.
