---
description: "Required MVP capabilities, harness statuses, and explicit exclusions."
last_verified: "2026-08-25"
---

# MVP scope

## Stage

The state of the work belongs to `docs/engineering/implementation-roadmap.md` and is not repeated here. This document answers a different question: what is and is not part of the MVP. A copy of the stage in two places has already diverged once and will diverge again: it becomes stale with every advance, with nobody positioned to notice.

The product contract, domain model, passports and versions, provider protocol, trust model, synchronization, CLI and API contracts, runbooks, quality gates, and Agent Skill have been agreed and accepted. There are no open contradictions among the specifications.

Implementation follows `docs/engineering/implementation-roadmap.md` and does not outrun its constraints: cloud publication does not begin before local schemas are immutable, and server-side work is parallelized only after the local-state and API schemas are frozen.

## Harnesses

| Status | Harnesses |
|---|---|
| Primary support | Claude Code, Codex, Grok Build |
| Beta | Pi, OpenCode, Cursor, Antigravity |
| Unknown | `undefined` without automatic installation |

Only primary support and completeness of the product requirements block the first release. Beta lines advance independently.

## Required

- CLI installation through a command from the website and `uv`;
- local registry on SQLite;
- PostgreSQL and RustFS/S3 in server mode;
- Google/GitHub OAuth;
- devices with an ID and key;
- developer, device, project, setup, and component passports;
- an index of a limited set of safe project text files;
- a limited symbol index for Python, TypeScript/JavaScript, Rust, Go, and Dart/Flutter;
- the complete `mvp-full` toolset during initial setup;
- anonymous reading of the public catalog;
- private drafts and cloud sync after auth;
- search by tags and structural filters;
- three trust lines with explicit consent to unverified content;
- arbitrary component composition;
- the `full-auto` execution profile;
- an increased number of confirmations in the configuration workflow;
- exact `X.Y` versions;
- backup, plan, apply, launch, status, and restore;
- importing an existing native configuration into a personal setup;
- the daily `status`, `rescan`, `search`, `diff`, `update`, and `rollback` cycle;
- access by account ID and invitations by verified email;
- web for the account and public catalog;
- reporting an object from the web and CLI into one closed moderation case;
- CLI removal with data retained and a separate purge;
- Agent Skill in Russian and English with a native projection for seven harnesses.

## Not included

- real payments and payouts;
- ratings and a social feed;
- browser-based setup editor;
- Windows runtime support;
- persistent desktop daemon;
- automatic updates and release channels;
- platform-authored packaging of third-party open-source components to populate the catalog;
- free-form tags outside the glossary;
- organization/team/enterprise landscape;
- a shared project setup for multiple developers and its review;
- ratings, public discussions, and automatic public issues from reports;
- direct model interface calls from `ai_stp`;
- vector representations, a call graph, and a complete semantic graph;
- APM or SX as a required core;
- automatic installation of objects from unverified authors;
- an absolute promise of no vulnerabilities.
