---
description: "Decision to install the complete toolset up front and index any safe text."
last_verified: "2026-08-04"
---

# ADR-0019: Complete toolset, complete index, and offline boundary

Status: accepted.

## Context

The previous requirements built the toolset from the needs of the project's active adapters, and the acceptance criterion explicitly required a minimal set. The second-level index parsed only Markdown, YAML, JSON, TOML, and TXT, while the limited third level covered five ecosystems.

This economy revealed two systemic defects. A new or documentation project receives a toolset that becomes insufficient as soon as code appears in it: changing the stack requires another download, hence network access, and breaks offline operation precisely when it is needed. Component selection also cannot see files that define the project: build configurations, scripts, source files, and native agent files were not among the parsed formats.

At the same time, the product promises full local operation without an account or server, but nowhere stated exactly what continues to work without network access and what stops working.

## Options

1. Retain the adaptive minimal set. This saves space and initial-setup time but shifts the cost to a moment when network access may be unavailable.
2. Install tools on demand at first use. This preserves minimality but makes offline operation unpredictable and turns indexing into a network operation.
3. Install one complete versioned profile up front and explicitly describe the offline boundary.

## Decision

Option 3 is accepted.

**Initial setup installs the `mvp-full` profile.** The profile includes language servers, linters, type checkers, analyzers, and scanners for Python, TypeScript and JavaScript, Rust, Go, and Dart and Flutter, as well as analyzers for information formats. Its composition is defined by a versioned policy rather than by the project's current contents.

**Artifact requirements are not relaxed.** Every tool has an exact version, source, integrity evidence, license, and supported-system matrix. Installation uses a versioned user directory, invocation uses an exact path, and `sudo` is not required.

**Any bounded safe text file is indexed** within the selected root. Structural parsing is applied to the five ecosystems and information formats; bounded metadata rather than invented structure is retained for other safe text files.

**Prohibitions remain.** Secrets, binary content, internal version-control directories, vendor directories, caches, and generated results are excluded by default. Limits on size, depth, and time remain mandatory.

**The offline boundary is fixed.** After successful initial setup, the following work without network access: passports, the project index, the local registry, imported objects, cached search, selection and building from local and cached candidates, checks with installed tools, bundle construction, the plan, provider application, state and recovery, and launching from cached artifacts.

Network access is required for the first uncached download, sign-in, uncached cloud search, access to private cloud objects, synchronization, publication, invitations and permissions, updating revocation information, and live verification of remote MCPs.

**Revocation does not destroy local data.** Revocation stops future cloud operations but does not delete local data or already verified cached bytes.

## Consequences

- `SPEC-004` changes the list of parsed formats to any bounded safe text while retaining the prohibitions;
- `SPEC-014` replaces the adaptive set with the `mvp-full` profile and gains an offline-boundary requirement;
- `docs/engineering/tech-stack.md` and the roadmap describe the complete profile instead of an on-demand set;
- an offline-operation matrix is introduced and referenced by product flows and runbooks;
- initial-setup validation lists the installed profile and confirms operation after network disconnection;
- the specific list of tool versions is selected during implementation from supported manifests rather than fixed in this decision.

## Reconsideration conditions

The decision shall be reconsidered if the complete profile's size or installation time becomes unacceptable on a typical developer machine, or if a way emerges to provably guarantee offline operation with on-demand installation.
