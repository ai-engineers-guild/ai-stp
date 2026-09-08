---
description: "The installed CLI bootstraps its pinned PyPI provenance verifier without manual tools."
last_verified: "2026-09-08"
---

# ADR-0171: Installed CLI owns index verification runtime

Status: accepted

## Context

The task selects one installed ai-stp CLI as the entry point for all seven
providers on Linux x86_64, Windows x86_64 and macOS arm64. The three other
OS/architecture pairs are not_verified. The existing PyPI reader requires a
separately installed verifier, and its CLI fallback drops the verified source
commit. Installing the verifier directly as a CLI dependency would make native
Windows ARM users build cryptography from source: inspected PyPI wheels do not
cover that platform.

## Decision

The CLI ships uv and a generated, hash-pinned verifier requirements file. It uses
uv to provision an isolated verifier environment in CLI-owned cache state and
runs the official pypi-attestations library there. No model interface or model
credential is involved. Provider bytes are fetched from PyPI and cryptographically
verified against the existing publisher policy before execution. Explicit GitHub
acquisition remains available; automatic acquisition uses the index and does not
silently change source after verification failure.

The verifier runs on a compatible managed Python on the three required platforms.
Windows ARM, Linux ARM and macOS x86_64 remain not_verified. Their absence from
qualification does not claim that their binaries cannot run, and does not impose
a manual compiler prerequisite on the supported installation path. Runtime
architecture is retained in the verification receipt.

The requirements file is exported from the workspace lock's provider-verifier
group, generated and drift-checked with the other CLI artifacts. Helper code uses
only that environment's official verifier library. It returns the identity and
source commit from the attestation that actually verified, including modern
Fulcio source-repository-digest claims.

## Consequences

Installing ai-stp-cli makes the loader available on the three required platforms without
manual gh, pypi-attestations or Rust installation. First index acquisition may
install the pinned helper runtime; subsequent use reuses its cache. Exact
artifact/provenance checks and typed failures remain. Removing the index path
removes uv's runtime ownership here, the verifier group and generated requirements.

This supersedes ADR-0141's choice of GitHub as the normal first acquisition path;
its provenance/trust rules remain unchanged. SPEC-008 and provider-release.md own
the executable acceptance and wire details.
