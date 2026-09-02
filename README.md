<p align="center">
  <strong>English</strong> · <a href="README.ru.md">Русский</a>
</p>

<p align="center">
  <img src="assets/readme/en/hero.png" width="100%" alt="ai-stp: select, verify and install a complete setup through your agent.">
</p>

<p align="center">
  <a href="https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml"><img src="https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml/badge.svg?branch=main" alt="check"></a>
  <a href="https://pypi.org/project/ai-stp-cli/"><img src="https://img.shields.io/pypi/v/ai-stp-cli" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="License: AGPL-3.0"></a>
  <a href="https://ai-stp.aiguild.space"><img src="https://img.shields.io/badge/catalog-ai--stp.aiguild.space-black" alt="catalog"></a>
</p>

The command is `ai-stp`. The distribution on PyPI is `ai-stp-cli`. The primary
consumer is the user's agent: every command returns one JSON envelope. `ai-stp`
does not call a model API and does not require a model key.

<p align="center">
  <img src="assets/readme/en/section-what.svg" width="100%" alt="01 One setup, eight kinds, exact versions">
</p>

<p align="center">
  <img src="assets/readme/shared/setup-core.png" width="100%" alt="A setup is a bound graph of components around one harness core.">
</p>

<p align="center">
  <img src="assets/readme/shared/kinds.png" width="100%" alt="Eight kinds: instruction, skill, mcp, hook, command, agent, plugin, setting.">
</p>

A **setup** belongs to one harness from creation. The eight kinds are
`instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`, `setting`.
Memory and rules are content of those kinds, not extra kinds. A published
version pins exact component versions and is immutable.

<p align="center">
  <img src="assets/readme/en/section-how.svg" width="100%" alt="02 CLI assembles. The provider writes.">
</p>

<p align="center">
  <img src="assets/readme/en/roles.svg" width="100%" alt="CLI plus agent select and bundle. Web owns account and catalog. Only the provider writes native harness state.">
</p>

<p align="center">
  <img src="assets/readme/shared/workflow.svg" width="100%" alt="install, passports, select, digest-bound plan and backup, provider apply, restore on failure.">
</p>

<p align="center">
  <img src="assets/readme/shared/trust-boundary.svg" width="100%" alt="Trust boundary: origin, version, consent.">
</p>

<p align="center">
  <img src="assets/readme/shared/compatibility-gate.svg" width="100%" alt="Compatibility gate: graph, target and policy must decide before apply.">
</p>

<p align="center">
  <img src="assets/readme/shared/immutable-artifact.svg" width="100%" alt="Published bytes are digested and stored as an immutable artifact.">
</p>

<p align="center">
  <img src="assets/readme/shared/signed-publication.svg" width="100%" alt="A publication binds digest, object version, policy and device.">
</p>

<p align="center">
  <img src="assets/readme/shared/sync-cursor.svg" width="100%" alt="Sync continues from the last confirmed cursor.">
</p>

Author verification is origin, not a safety verdict on the bytes.
`author_verified` and `component_verified` are independent.

<p align="center">
  <img src="assets/readme/en/modes.svg" width="100%" alt="Local without an account, anonymous catalog reads, signed-in private sync and publication.">
</p>

<p align="center">
  <img src="assets/readme/en/section-use.svg" width="100%" alt="03 Install the CLI, then let the agent drive it">
</p>

```bash
uv tool install ai-stp-cli
ai-stp doctor --json
```

<details>
<summary>Next commands the agent should read from the machine registry</summary>

```bash
ai-stp help --agent --json
ai-stp passport developer init --json
ai-stp device init --json
```

`ai-stp` is the executable. `ai-stp-cli` is the package name. Copying
`uv tool install ai-stp` installs a distribution this project does not publish.

</details>

## Supported harnesses

| Status | Harnesses |
|---|---|
| Primary support | Claude Code, Codex, Grok Build |
| Beta support | Pi, OpenCode, Cursor, Antigravity |
| Limited mode | `undefined` for an unknown harness |

Automatic install is refused for an unknown harness.

## Strategic direction: Rust and a Pi-inspired plugin architecture

**By 31 December 2026, `ai-stp` will be rewritten in Rust and migrated to a
plugin-first architecture inspired by Pi.** The migration will preserve the
public CLI and API contracts while separating a lightweight, deterministic
core from versioned plugins for harnesses, components, projections, and
provider-specific integrations.

<details>
<summary>Stage, contributing, documentation</summary>

Phase status belongs to
[`docs/engineering/implementation-roadmap.md`](docs/engineering/implementation-roadmap.md):
read that file when you need the current evidence, not a summary here.

- [CONTRIBUTING.md](CONTRIBUTING.md): how changes enter this repository.
- [SECURITY.md](SECURITY.md): how to report a vulnerability.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): expectations for participation.
- [AGENTS.md](AGENTS.md): rules for people and agents. Read before any repository change.
- [docs/index.md](docs/index.md): map of product, architecture, contract, engineering, and operations documentation.
- [docs/product/vision.md](docs/product/vision.md): the problem, users, value, and positioning of ai_stp.
- [docs/product/scope.md](docs/product/scope.md): required MVP capabilities, harness statuses, and explicit exclusions.
- [docs/architecture/overview.md](docs/architecture/overview.md): overall data flow and the boundaries of the local and server environments.
- [specs/index.md](specs/index.md): versioned requirements that the code must satisfy.
- User docs: [English](https://ai-stp.aiguild.space/en/docs) · [Русский](https://ai-stp.aiguild.space/ru/docs)

</details>

<details>
<summary>License</summary>

AGPL-3.0-or-later. Network use of the platform is covered: if `ai-stp` is
offered as a service, the source of the modified version stays available to
those users.

The catalog belongs to the guild. Public harness providers are separate
projects under their own licenses.

Components and setups published by users are independent works licensed by
their authors; the platform license does not apply to them.

</details>
