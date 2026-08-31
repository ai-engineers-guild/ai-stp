---
description: "Versioned provider network boundary and honest evidence of its enforcement."
last_verified: "2026-08-09"
---

# ADR-0047: Provider Network Capability

Status: accepted; v2 models, the closed wire schema, phase invoker, and verifiable
Linux/Bubblewrap launcher are implemented; the macOS launcher is not yet implemented;
protocol v1 is unchanged.

## Context

The frozen provider protocol v1 restricts the argument array, shell, executable,
target directory, environment, time, and output size. It does not declare an action's
network requirement or isolate the process network. Therefore, a successful launch
through the current boundary is not evidence that network access was absent, and
protocol v1 does not address the network class of the `#184` malicious corpus.

Some actions must be entirely local. Other actions may legitimately download the
harness program or launch an environment whose normal operation accesses external
services. One implicit mode either breaks valid actions or creates a false sandbox
promise. A portable way to deny network access to a process also differs between
Linux and macOS; the presence of the OS alone does not prove that such a mechanism
exists.

## Decision

Protocol v1 remains frozen. In it, the network state is "unspecified and unproven";
no network fields are added to the current `Boundary`, `provider-info`, or action
result.

Provider protocol v2 introduces a mandatory declaration for every action:

- `network_requirement = none` — the action must run without network access;
- `network_requirement = artifact_download` — the action is explicitly allowed to
  fetch an artifact in a separate installation or update phase;
- `network_requirement = runtime_external` — an external runtime is part of the
  requested launch.

The launch result contains one of these states:

- `network_enforcement = enforced` — the required isolation was actually installed
  and verified by the selected launcher;
- `network_enforcement = unavailable` — the environment cannot verifiably install
  the required isolation;
- `network_enforcement = not_requested` — policy explicitly allowed the required
  network and no prohibition was requested.

`none` runs only with an `enforced` result. If capability discovery does not find a
verified launcher, the CLI returns a typed refusal **before launching** the provider.
`unavailable` is never converted into `enforced` or described as "network denied."
`artifact_download` and `runtime_external` grant the provider no new secrets: the
existing environment allowlist and separate credential rules remain in effect.

The action set and its requirements are a closed part of v2. The preliminary mapping
that must be fixed in conformance fixtures before implementation is:

| Actions | Requirement |
|---|---|
| `provider-info`, `software-status`, `validate-bundle`, `plan-bundle`, `apply-bundle`, `status`, `restore` | `none` |
| `software-plan` | `none` |
| `software-install`, `software-update` | `artifact_download` only for the explicit download phase; local checks and target modification remain `none` |
| `software-remove` | `none` |
| `launch` | `runtime_external` |

Separating the download phase is mandatory: allowing network access for the download
does not extend it to the entire subsequent apply operation.

A v2 wire invocation always contains `--phase <phase>` before the mandatory
`--target <absolute-directory>`. The consumer selects v2 from an already verified
release manifest or an explicit conformance mode before the first process launch. It
does not trust `protocol_version` from an unknown provider's response when selecting
a more privileged boundary. `network_enforcement` is an observation by the consumer
and is stored alongside the provider payload, rather than accepted from it as proof.

## Capability and Evidence

Linux and macOS have separate capability probes and negative tests. The mechanism's
name or the presence of a binary is insufficient: the test launches a process that
attempts to access a controlled address and observes failure inside the same boundary
that will subsequently launch the provider.

Linux uses a Bubblewrap network namespace only after a positive control and checks
for IPv4, IPv6, and DNS over UDP. A separate system sandbox or virtualized boundary
still needs to be selected for macOS. Neither option is considered available without
checking the OS version, authority, and observable network behavior. If no verified
mechanism exists, the capability is `unavailable` and an action with `none` does not
run.

The Bubblewrap executable and its entire directory chain to the root must be owned by
`root` and not be group/world-writable. A launcher from the user's `PATH` does not
receive `enforced` status even if it reproduces the expected probe output: the same
user could replace it between the probe and provider invocation.

## Compatibility and Migration Order

1. Add v2 models, schemas, and a typed pre-invocation refusal to `ai_stp` without
   changing `VERSION = 1` or the v1 wire shape. This step is implemented in
   `ai_stp_cli.provider.protocol_v2`; network probes are intentionally not attributed
   to it.
2. Implement capability probes and launchers on Linux and macOS; prove fail-closed,
   DNS, IPv4, and IPv6 behavior with negative tests. The Linux/Bubblewrap path is
   implemented with a positive control and external observation of a DNS-over-UDP
   packet; macOS remains outstanding.
3. Teach the consumer to select v1 or v2 explicitly. `provider conformance` accepts
   only explicit version 1 or 2; the phase invoker applies the selected v2 policy to
   the real process, while the v2 runner checks the complete phase declaration and
   consumer decisions. The runner itself executes only no-effect phases on the
   literal ZIP corpus; mutating phases are checked in provider E2E against a
   disposable target. This step is also implemented for the install lifecycle: the
   version and absolute provider target enter the plan digest, while apply/resume do
   not accept a new version selection. v1 remains for legacy compatibility, but does
   not satisfy the `#184` release gate and is not used to close it.
4. Release Claude Code and Codex providers with protocol v2 and conformance evidence;
   then pin signed releases and anti-rollback.
5. Switch the release policy for primary providers to mandatory v2. Removal of v1 is
   performed only by a separate decision after a declared compatibility window.

Neither the consumer nor the provider guesses an unknown version. Dual-stack means
two explicit schemas and two sets of conformance fixtures, not extended v1 parsing.

## Consequences

Until a launcher is implemented and proven on a specific OS, documentation and the
interface cannot promise provider network denial. The presence of the v2 model alone
is not enforcement. Linux evidence does not transfer to macOS.
Having a signed first-party provider reduces substitution risk, but does not replace
isolation or address the network class of `#184`.

Fail-closed behavior may temporarily make local provider actions unavailable on a
system without a verified launcher. This is intentional: an honest refusal is safer
than a false `enforced` result. Real provider releases and macOS evidence depend on
this implementation.

## Reconsideration Conditions

The decision will be reconsidered if the provider protocol stops launching an
external process, or if one trusted runtime provides equally verifiable network
isolation on all supported systems.
