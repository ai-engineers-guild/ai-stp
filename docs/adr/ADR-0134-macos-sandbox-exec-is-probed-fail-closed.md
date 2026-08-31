---
description: "Decision to use the system sandbox-exec on macOS only after a native network-denial probe and never fall back to a trust exception."
last_verified: "2026-08-31"
---

# ADR-0134: macOS sandbox-exec is probed and fails closed

Status: accepted. Resolves the macOS debt in `ADR-0126`.

## Context

On Linux the consumer proves Bubblewrap; on Windows it proves AppContainer.
macOS previously allowed the trusted-release local phase without network
isolation. Current macOS still provides `/usr/bin/sandbox-exec`; a Seatbelt
profile can deny network access to an unprivileged process tree, but the
interface and SBPL language are deprecated/private surface.

The presence of an executable therefore does not prove capability. An
observation cannot be transferred from one macOS version to another, and a
launch cannot be called `enforced` until the same host passes both positive and
negative controls.

## Decision

The consumer uses only the system `/usr/bin/sandbox-exec` when the executable
and all its ancestors belong to `root` and are not writable by the group or
others. The closed profile allows the existing file/process surface and denies
`network*`:

```scheme
(version 1)
(allow default)
(deny network*)
```

Before the first provider spawn, the consumer proves on the current machine:

1. the unsandboxed parent reaches local IPv4, IPv6, and DNS-like UDP controls;
2. the same Python child and endpoints are unreachable under the profile;
3. the executable has the exact SHA-256 recorded in evidence.

Only the complete result becomes `network_enforcement=enforced` and
`v3_local_phase=network_denied`. A missing executable, untrusted path, SBPL
error, or ambiguous probe remains `unavailable`; the local v3 phase refuses
before provider spawn. macOS is removed from `UNISOLATED_PLATFORMS`, so
`trusted_release` and `explicit_unverified_provider` no longer bypass refusal.

## Consequences

- deprecated/private surface does not become a permanent promise: capability is
  measured for each consumer process and may honestly become `unavailable`;
- fallback does not replace a missing mechanism with trust in provider bytes;
- the profile limits only network access. Target ownership, exact argv,
  environment, timeout, and output bounds remain in the existing provider
  contract;
- the native macOS matrix is mandatory evidence. Linux or a mock cannot prove
  that current macOS accepts the profile and blocks transport.

## Review conditions

This decision is replaced when macOS publishes a supported arbitrary-process
sandbox API with at least the same fail-closed property or removes
`sandbox-exec`/SBPL. In either case the consumer first adds a native probe of
the new mechanism instead of transferring `enforced` by API name.
