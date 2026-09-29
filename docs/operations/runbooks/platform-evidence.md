---
description: "Native platform evidence for the exact CLI candidate without publish or deploy authority."
last_verified: "2026-09-29"
---

# Platform evidence

Manual workflow `platform-evidence.yml` proves the CLI/package and consumer
network boundary on the supported native platforms. It does not publish to
PyPI, promote a deploy, or replace the setup-systems-owned provider lifecycle.

## Build leg

`build-exact-candidate` on `ubuntu-24.04` runs
`release_scripts/build_candidate.py --replace` and uploads
`dist/release-candidate/` untouched. The candidate is one `ai-stp-cli` wheel
and sdist plus the manifest, SHA-256 sums, SBOM, and evidence JSON: every
first-party module ships inside that wheel (`ADR-0146`), and the verifier
refuses a candidate carrying any other wheel.

## Verify legs

| Runner | Native row | Python |
|---|---|---|
| `ubuntu-24.04` | Linux/x86_64 | 3.14 |
| `macos-15` | macOS/arm64 | 3.14 |
| `windows-2025` | Windows/x86_64 | 3.14 |
| `ubuntu-24.04` | Linux/x86_64 | 3.12 (floor) |

Each leg proves the runner identity by comparing `platform.system()` and
`platform.machine()` with the expected OS/architecture — x64 emulation on ARM
does not count — then installs the pinned native `uv` into an isolated
`UV_PROJECT_ENVIRONMENT` under `RUNNER_TEMP` and runs
`release_scripts/verify_candidate_install` on the downloaded artifact. That
installs the exact wheel outside the checkout, executes the machine commands,
checks the bundled modules and their PEP 610 provenance, records the network
report, and proves the executable is gone after `uv tool uninstall` while user
data is preserved. Every leg runs with
`AI_STP_FORCE_FILE_CREDENTIAL_STORE=1`.

## Provider network boundary

Each leg then runs `release_scripts/verify_network_evidence` on the recorded
report. The accepted states are exact, per operating system:

- **enforced** — an isolation launcher exists and the v3 local phase is denied
  network. On Linux the leg installs Bubblewrap first, so this is the expected
  answer there.
- **unisolated by trust** — only Windows may answer this, and only with the
  exact reasons `explicit_unverified_provider` and `trusted_release`.
- **refused** — no launcher and no trust basis: the operation is denied rather
  than run unisolated. This is the expected answer on macOS, and on a Linux
  leg where the launcher is missing.

Anything else — an unknown enforcement state, a missing reason, an unisolated
run where the trust exception does not apply — fails the leg.

## Separate producer evidence

The complete provider plan/apply/status/recovery/rollback belongs to the
workflows of the seven setup systems. Their runs link to the same platform
rows, but are not embedded in this workflow and do not inherit its success.
Final consumer release evidence combines the two exact results after the
producer release.

## Artifact

Record repository/ref/SHA, runner image/OS/architecture, Python/uv, the
candidate file digests, PEP 610 provenance, the network report and its
verification verdict, and all `not_verified` reasons. A workflow existing
successfully without a run on the candidate proves nothing.
