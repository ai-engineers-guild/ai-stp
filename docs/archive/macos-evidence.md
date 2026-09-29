---
description: "Collecting CLI/package evidence on a standard GitHub-hosted macOS runner."
last_verified: "2026-08-18"
---

# Future CLI evidence on macOS

## Boundary

Under `ADR-0062`, macOS is outside the current support matrix and does not block
the current Linux x86_64 release profile. Workflow `macos-evidence.yml` remains
an honest future portability gate and proves only the CLI/package slice: Python
3.12 and 3.14, static checks, SQLite/local tests, the cross-platform
HarnessBundle oracle, wheel, `uv tool`, Agent Skill, the exact five-wheel
release candidate, and preservation of local data after uninstall. Each matrix
row gets a separate `UV_PROJECT_ENVIRONMENT` under `RUNNER_TEMP` and verifies
the actual Python version inside the installed CLI; a stale persistent-runner
environment cannot substitute for the matrix.

It does not cover Claude Code/Codex provider E2E, protocol v2 network
enforcement, or PyPI publication. That evidence requires exact signed provider
releases and separate release authorization under `release-evidence.md`.

## Preconditions

1. Use only the standard GitHub-hosted `macos-15`; do not register a dedicated
   persistent self-hosted macOS runner.
2. Do not give the job a deployment SSH route, PyPI identity, or persistent secrets.
3. The workflow installs Python and `uv` over the standard runner image.
4. Ensure the working account has no Keychain entries needed by the test. The
   workflow also sets `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1`, so the regression
   must operate only inside a temporary directory.

## Run

Run workflow `macos-evidence` manually on the exact commit. The matrix runs
sequentially on ephemeral hosted workers for Python 3.12 and 3.14. The workflow
performs no push, deployment, or publication.

The `-m "not platform"` selection excludes the server/PostgreSQL slice: absence
of Docker on a macOS machine does not become a fictitious platform success. The
full platform gate remains on Linux; the macOS run proves only the claimed CLI
portability.

## Evidence acceptance

Retain for every matrix job:

- exact repository/ref/SHA and a clean checkout;
- `RUNNER_NAME`, `uname -a`, `sw_vers`, architecture, and Python version;
- complete `back-static` result and the number of passed/skipped CLI tests;
- JUnit artifact, distribution hashes, and installation result outside checkout;
- manifest, checksums, and JSON evidence for the exact five-wheel candidate,
  including PEP 610 provenance and the actual Python version;
- Agent Skill install/status/remove and registry preservation after `uv tool uninstall`;
- literal ZIP bytes, `bundle_digest`, and `artifact_digest` from
  `test_bundle_cross_platform_golden.py`;
- every skipped/not-run reason and residual risk.

This workflow is needed until macOS is added to the support matrix. By itself it
does not close issues `#167`, `#175`, and `#176` for the current Linux x86_64
profile and does not replace Linux provider E2E.

## Current state

Since `2026-08-18`, the workflow has used `macos-15` as the standard fallback.
After a Drakkars macOS class appears, this sole `runs-on` target must be
replaced with the corresponding scale-set name.
