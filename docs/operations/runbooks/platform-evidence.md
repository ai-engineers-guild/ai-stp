---
description: "Six-leg platform evidence for the exact CLI candidate without publish or deploy authority."
last_verified: "2026-08-31"
---

# Platform evidence

Manual workflow `platform-evidence.yml` proves the CLI/package and consumer
network boundary on Linux, Windows, and macOS for both architectures. It does
not publish to PyPI, promote a deploy, or replace the setup-systems-owned
provider lifecycle.

## Six native legs

| Runner | Native row |
|---|---|
| `ubuntu-24.04` | Linux/x86_64 |
| `ubuntu-24.04-arm` | Linux/arm64 |
| `windows-2025` | Windows/x86_64 |
| `windows-11-arm` | Windows/arm64 |
| `macos-15-intel` | macOS/x86_64 |
| `macos-15` | macOS/arm64 |

Each job checks `RUNNER_ARCH`, uses an isolated environment, native `uv`, five
exact candidate wheels, and temporary credential storage. x64 emulation on ARM
does not count.

## What runs

- build and install the exact five-wheel CLI candidate outside the checkout;
- machine commands and actual Python/OS/architecture identity;
- portable bundle oracle and uninstall while preserving user data;
- `provider network` and runtime probes of the consumer boundary.

Linux must prove Bubblewrap or refuse early. Windows uses AppContainer with
runtime proof and fail-closed behavior. macOS proves the system
`sandbox-exec` with the same transport probe; a missing executable or proof is
an early refusal, not a reason to run unisolated.

## Separate producer evidence

The complete provider plan/apply/status/recovery/rollback belongs to the
workflows of the seven setup systems. Their six-leg runs link to the same
platform rows, but are not embedded in this workflow and do not inherit its
success. Final consumer release evidence combines two exact results after the
producer release.

## Artifact

Record repository/ref/SHA, runner image/OS/architecture, Python/uv,
distribution digests, PEP 610 provenance, bundle/provider network digests, and
all `not_verified` reasons. A workflow existing successfully without a run on
the candidate proves nothing.
