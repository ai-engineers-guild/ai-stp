# ai_stp

`ai_stp` is a system for creating, validating, storing, selecting, and installing complete AI harness configurations.

The primary product consumer is the user's agent operating through the CLI. Under `ADR-0018`, the web owns the account and public catalog: profile and privacy, devices and revocation, owned objects, publication, permissions, reports, and minimal administration. Passport creation, indexing, selection, assembly, validation, and installation remain with the CLI and agent; the web displays their results but does not perform them.

## Strategic direction: Rust and a Pi-inspired plugin architecture

**By 31 December 2026, `ai-stp` will be rewritten in Rust and migrated to a plugin-first architecture inspired by Pi.**

The migration will preserve the public CLI and API contracts while separating a lightweight, deterministic core from versioned plugins for harnesses, components, projections, and provider-specific integrations.

## What is a setup

A setup is the complete configuration of a specific harness:

- system instructions (`AGENTS.md`, `CLAUDE.md`, and equivalents);
- skills;
- MCP servers and their settings;
- hooks;
- commands;
- agents and subagents;
- plugins and marketplaces, where supported by the harness;
- memory, rules, settings, and auxiliary tools.

Each installable setup version is bound to a specific harness, harness version, operating system, exact component versions, and validation results.

## MVP

Supported harnesses:

| Status | Harnesses |
|---|---|
| Primary support | Claude Code, Codex, Grok Build |
| Beta support | Pi, OpenCode, Cursor, Antigravity |
| Limited mode | `undefined` for an unknown harness |

Primary flow:

```text
install CLI
→ discover environment and harness
→ developer and device passports
→ project index
→ find and assemble setup
→ validation
→ installation plan
→ backup
→ apply through the harness provider
→ launch and verify state
→ restore on failure
→ optional cloud synchronization
```

## Local and cloud modes

Without an account, the following are available:

- local registry;
- passports;
- project indexing;
- read-only public catalog;
- selection and installation of public objects.

After authentication through Google or GitHub, the following are available:

- cloud copy of the personal registry;
- private setups and components;
- publication;
- devices and their keys;
- access grants by account identifier and invitations to verified email addresses;
- reports on catalog objects.

## Stage

The sole owner of the current phase status is
[`docs/engineering/implementation-roadmap.md`](docs/engineering/implementation-roadmap.md).
README does not copy its table: CLI, platform, and release-evidence mechanisms progress at
different rates, and a single “done” statement would hide outstanding external evidence.

The repository already contains an executable local-first CLI flow, provider consumer framework,
and Sprint-1 server/web slice. The roadmap separates the implemented core from the remaining server
contracts, real provider releases, OAuth/device E2E, and release gates. The currently
proven release profile is Linux x86_64 under `ADR-0062`; macOS is not claimed as
supported without separate evidence. A mock or stale deployed SHA does not
satisfy the corresponding external criterion.

Development takes place in contributors' personal branches—`rldyourmnd` (Danil) and `letya999`
(Artyom)—with PRs into `main`. `main` is the only line; there is no separate integration
branch. The process is described in `docs/engineering/git-workflow.md`.

## Documentation

Start with:

- [AGENTS.md](AGENTS.md): rules for people and agents. Read before any repository change.
- [docs/index.md](docs/index.md): map of product, architecture, contract, engineering, and operations documentation.
- [docs/product/vision.md](docs/product/vision.md): the ai_stp problem, users, value, and positioning.
- [docs/product/scope.md](docs/product/scope.md): required MVP capabilities, harness statuses, and explicit exclusions.
- [docs/architecture/overview.md](docs/architecture/overview.md): overall data flow and boundaries between local and server systems.
- [specs/index.md](specs/index.md): versioned requirements that the code must satisfy.

## License

AGPL-3.0-or-later. The license also covers network use of the platform: if `ai_stp` is offered to users as a service, the source code of the modified version remains available to them.

The catalog belongs to the guild. NDDev provides public harness providers; they remain separate projects under their own licenses and are not relicensed by this repository.

Components and setups published by users are independent works licensed by their authors; the platform license does not apply to them.
