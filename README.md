# ai-stp

**Build, verify, store, select and install complete AI harness setups — through your agent.**

[![check](https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml/badge.svg?branch=main)](https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml)
[![PyPI](https://img.shields.io/pypi/v/ai-stp-cli)](https://pypi.org/project/ai-stp-cli/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![site](https://img.shields.io/badge/catalog-ai--stp.aiguild.space-black)](https://ai-stp.aiguild.space)

An [AI Engineers Guild](https://github.com/ai-engineers-guild) project. The
primary consumer is the user's agent operating through a strict machine CLI:
every command answers one JSON envelope with typed errors and explicit next
actions. The web application owns the account and the public catalog — profile,
devices, publication, permissions, reports — and displays results; passport
creation, indexing, selection, assembly, validation and installation belong to
the CLI and the agent.

## Quick start

```bash
pipx install ai-stp-cli          # or: pip install ai-stp-cli

ai-stp help --agent --json       # the full machine command registry
ai-stp toolchain harnesses --json
ai-stp component discover --root . --json
ai-stp project passport --root . --json
```

Every command takes `--json` and is designed to be driven by an agent; the
same registry powers the human help.

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

Each installable setup version is bound to a specific harness, harness version,
operating system, exact component versions, and validation results.

## Supported harnesses

| Status | Harnesses |
|---|---|
| Primary support | Claude Code, Codex, Grok Build |
| Beta support | Pi, OpenCode, Cursor, Antigravity |
| Limited mode | `undefined` for an unknown harness |

The final native state of a harness is written only by its public provider — a
released, signed setup-system executable. `ai-stp` validates the component
graph, builds a deterministic bundle, and drives the provider through a
digest-bound plan with backup and rollback. Providers live in
[NDDev-OpenNetwork](https://github.com/NDDev-OpenNetwork) as separate projects
under their own licenses.

## Primary flow

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

Without an account: local registry, passports, project indexing, read-only
public catalog, selection and installation of public objects.

After authentication through Google or GitHub: cloud copy of the personal
registry, private setups and components, publication, devices and their keys,
access grants by account identifier and invitations to verified email
addresses, reports on catalog objects.

`ai-stp` calls no model API and requires no model key.

## Strategic direction: Rust and a Pi-inspired plugin architecture

**By 31 December 2026, `ai-stp` will be rewritten in Rust and migrated to a
plugin-first architecture inspired by Pi.** The migration will preserve the
public CLI and API contracts while separating a lightweight, deterministic
core from versioned plugins for harnesses, components, projections, and
provider-specific integrations.

## Stage

The sole owner of the current phase status is
[`docs/engineering/implementation-roadmap.md`](docs/engineering/implementation-roadmap.md).
This README does not copy its table: CLI, platform, and release-evidence
mechanisms progress at different rates, and a single "done" statement would
hide outstanding external evidence. The currently proven release profile is
Linux x86_64 under `ADR-0062`; other profiles are claimed only with separate
evidence.

## Development

Development takes place in contributors' personal branches — `rldyourmnd`
(Danil) and `letya999` (Artyom) — with PRs into `main`. `main` is the only
line; there is no separate integration branch. The process is described in
[`docs/engineering/git-workflow.md`](docs/engineering/git-workflow.md).

- [CONTRIBUTING.md](CONTRIBUTING.md): how changes enter this repository.
- [SECURITY.md](SECURITY.md): how to report a vulnerability.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): expectations for participation.

## Documentation

Start with:

- [AGENTS.md](AGENTS.md): rules for people and agents. Read before any repository change.
- [docs/index.md](docs/index.md): map of product, architecture, contract, engineering, and operations documentation.
- [docs/product/vision.md](docs/product/vision.md): the problem, users, value, and positioning.
- [docs/product/scope.md](docs/product/scope.md): required MVP capabilities, harness statuses, and explicit exclusions.
- [docs/architecture/overview.md](docs/architecture/overview.md): overall data flow and boundaries between local and server systems.
- [specs/index.md](specs/index.md): versioned requirements that the code must satisfy.

## License

AGPL-3.0-or-later. The license also covers network use of the platform: if
`ai-stp` is offered to users as a service, the source code of the modified
version remains available to them.

The catalog belongs to the guild. NDDev provides public harness providers;
they remain separate projects under their own licenses and are not relicensed
by this repository.

Components and setups published by users are independent works licensed by
their authors; the platform license does not apply to them.
