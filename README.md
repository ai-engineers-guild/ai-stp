<p align="center">
  <strong>English</strong> · <a href="README.ru.md">Русский</a>
</p>

<p align="center">
  <img src="assets/readme/en/hero.svg" width="640" alt="ai-stp: select, verify and install a complete setup through your agent.">
</p>

<p align="center">
  <a href="https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml"><img src="https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml/badge.svg?branch=main" alt="check"></a>
  <a href="https://github.com/ai-engineers-guild/ai-stp/releases?q=cli-v"><img src="https://img.shields.io/badge/CLI-Rust-orange" alt="Rust CLI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="License: AGPL-3.0"></a>
  <a href="https://ai-stp.aiguild.space"><img src="https://img.shields.io/badge/catalog-ai--stp.aiguild.space-black" alt="catalog"></a>
</p>

The command is `ai-stp`, a standalone Rust executable. The primary consumer is
the user's agent: every command returns one JSON envelope. It needs no Python
runtime or model key and does not call a model API.

## One setup, nine kinds, exact versions

<p align="center">
  <img src="assets/readme/shared/kinds.svg" width="640" alt="Nine kinds: instruction, skill, mcp, hook, command, agent, plugin, setting, cli.">
</p>

A **setup** belongs to one harness from creation. The closed kinds are
`instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`, `setting`,
`cli`. `command` is a named slash invocation; `cli` is a standalone executable.
Memory and rules are content of those kinds, not extra kinds. A published
version pins exact component versions and is immutable.

## CLI assembles, the provider writes

The CLI and the agent select, validate, and bundle. Every command is one JSON
envelope. The CLI does not write the harness's native files. The web owns the
account and the public catalog; it does not assemble or install a setup. Only
the harness provider writes native state.

<p align="center">
  <img src="assets/readme/shared/workflow.svg" width="640" alt="Eight kinds pin into one setup for one harness. The CLI validates and bundles. Only the provider writes native files.">
</p>

Trust is origin, version, and consent. Compatibility — graph, target, and
policy — must decide before apply. A published version is an immutable digest
bound to object version, policy, and device. Sync continues from the last
confirmed cursor. Author verification is origin, not a safety verdict on the
bytes. `author_verified` and `component_verified` are independent.

Local work needs no account. The public catalog is readable anonymously. Google
or GitHub sign-in unlocks private objects, sync, publication, devices, and
grants.

## Install the CLI, then let the agent drive it

Download the native archive for your platform from
[GitHub Releases](https://github.com/ai-engineers-guild/ai-stp/releases?q=cli-v).
Verify its checksum and build attestation, then follow the
[native installation instructions](apps/cli-v2/README.md#install-and-update).
For a fresh local identity:

```sh
ai-stp init --credential-store os_keyring --json
ai-stp task intents --json
```

Existing Python installations require the explicit in-place state transfer
in the [CLI guide](apps/cli-v2/README.md#state-and-first-run). Their SQLite data
and device key are preserved; the old writer is fenced. PyPI's historical
`ai-stp-cli` wheel is not the current installation route.

Use `task input-schema` for exact author/install inputs and
`help --agent --json` for the implemented expert commands. Setup systems are
installation components acquired by this CLI; no second setup-manager install
is needed. Harness executables remain managed by the user and their vendors.

## Desktop application

`apps/desktop` is `ai-stp-desktop`, a Tauri 2 desktop shell over the
same CLI machine contract — catalog, task-engine journeys, targets, and
recovery in a native window for Linux, macOS, and Windows. Release
bundles embed the CLI as a sidecar, so no separate install is required.
Download the latest build from
[GitHub Releases](https://github.com/ai-engineers-guild/ai-stp/releases?q=desktop)
(bundles are unsigned; `SHA256SUMS` covers every artifact). Details and
the boundary rules live in `apps/desktop/README.md` and ADR-0222.

## Platform and harness support

The Rust CLI builds and runs in Linux x86-64, Apple Silicon macOS and Windows
x86-64 CI. Isolated setup installation and active-session handoff are currently
implemented on Linux; macOS and Windows return an explicit refusal for that
boundary. `capabilities` reports the current platform rather than assuming that
a successful binary build proves provider execution.

The managed installation components cover Claude Code, Codex, Grok Build, Pi,
OpenCode, Cursor and Antigravity. `provider inspect` and mechanical selection
checks determine the exact supported kinds and configuration surfaces for an
operation. Unknown or incompatible surfaces refuse before publication.

The [Rust CLI guide](apps/cli-v2/README.md) owns installation, migration,
recovery and platform details. The executable registry owns command parameters.

`main` is the protected release branch; work starts from `dev` and enters it by
PR before promotion to `main`. For a new workstation, follow
[CONTRIBUTING.md](CONTRIBUTING.md#development-on-a-new-workstation).

Phase status belongs to
[`docs/engineering/implementation-roadmap.md`](docs/engineering/implementation-roadmap.md):
read that file when you need the current evidence, not a summary here.

<details>
<summary>Contributing</summary>

- [CONTRIBUTING.md](CONTRIBUTING.md): how changes enter this repository.
- [SECURITY.md](SECURITY.md): how to report a vulnerability.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): expectations for participation.
- [AGENTS.md](AGENTS.md): rules for people and agents. Read before any repository change.

</details>

<details>
<summary>Documentation</summary>

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

The catalog belongs to the guild. Public harness installation components
retain their separate repositories and licenses.

Components and setups published by users are independent works licensed by
their authors; the platform license does not apply to them.

</details>
