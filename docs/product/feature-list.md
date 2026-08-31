---
description: "MVP functional areas and their observable outcomes."
last_verified: "2026-08-04"
---

# MVP capabilities

## Installation and environment

- installation of `ai_stp` through `uv`;
- user directories without mandatory `sudo`;
- installation and updating of versioned provider releases;
- installation of the complete `mvp-full` profile toolset during initial setup;
- detection of OS, architecture, harnesses, and versions through declared detectors;
- safe uninstall and a separate purge.

## Passports and index

- discovery of safe facts and findings by the CLI;
- a device passport with the observed environment and a separate summary for each device;
- assembly of the developer passport by the user's agent without a model call from `ai_stp`;
- questions only for unknown required fields and risky decisions;
- registration of selected Git projects and a limited discovery root;
- extraction of the stack, versions, commands, and AI components;
- an index of limited safe text files and a limited symbol index;
- provenance and verification of each significant fact as two axes.

## Catalog

- local registry;
- public cloud registry readable without an account;
- the guild's first-party launch catalog as a release barrier;
- private drafts and objects after auth;
- mandatory normalized tags on a published version;
- Git provenance with an exact commit and subpath for a public version;
- exact digest;
- a separately maintained public profile;
- grants by account ID and invitations by verified email;
- permissions on the major line: read, install, and fork without editing the original;
- derivative publication only with a substantive change and complete verification.

## Search, selection, and assembly

- search by name, description, tags, and synonyms with prefix and phrase queries;
- structural filters by kind, harness, compatibility, source, trust line, and the two verification axes;
- hard filters before any ranking;
- the `authoritative` line by default;
- the `experimental` line only with explicit consent and in a separate section;
- durable consent exceptions only by publisher or object major line, with a new decision when permissions expand;
- direct selection of an owned, imported, or exactly pinned object;
- arbitrary component graph;
- adaptation through overlays;
- conflict and conversion reports;
- a decision trace with the line, consent, and reasons;
- short-lived composition proposals and confirmation that fixes a private setup version;
- a simple deterministic MVP assembler: a semantic conflict blocks the package rather than being merged automatically;
- a deterministic native bundle.

## Installation and daily work

- the `full-auto` execution profile;
- isolated target by default;
- live target only as an explicitly selected mode;
- side-effect-free plan;
- backup, apply, launch, status, and restore;
- importing an existing native configuration into a personal setup;
- notification of missing required environment variables without reading their values;
- the daily `status`, `rescan`, `search`, `diff`, `update`, and `rollback` cycle only by user decision.

## Synchronization

- device ID and key;
- revision graph;
- fast-forward push/pull;
- field-aware three-way merge;
- explicit conflicts;
- tombstones;
- offline local data after revoke.

## Web

- landing and installation command;
- sign-in through Google and GitHub;
- public search, cards, passports, compatibility, and verification summary;
- public profiles;
- account profile, public profile, and privacy settings;
- devices and their revocation;
- the user's own drafts, objects, and versions;
- publication and its state;
- synchronization state;
- granting and revoking access and invitations;
- reporting an object and the state of the user's own reports;
- minimal administrative actions with auditing, including report triage.

Creating and changing passports, project indexing, selection, assembly, verification, and installation remain with the CLI and agent. `ADR-0018` defines the ownership boundary.
