# ai-stp

[Русский](README.ru.md) · [Catalog](https://ai-stp.aiguild.space) ·
[CLI releases](https://github.com/ai-engineers-guild/ai-stp/releases?q=cli-v)

ai-stp is a Rust CLI for creating, validating, selecting and installing complete
AI harness configurations. The primary consumer is your coding agent. Local work
needs no account, Python runtime or model key. The web provides accounts and the
public catalog; the CLI remains the engine.

## Start

Download a native archive, verify its checksum and GitHub attestation, and follow
[installation and state setup](apps/cli/README.md#install-and-update).

```sh
ai-stp init --credential-store os_keyring --json
ai-stp task intents --json
ai-stp help --agent --json
```

Existing Python state requires the explicit in-place transfer described in the
[CLI guide](apps/cli/README.md#state-and-first-run). Historical PyPI wheels are
not the current installation route. The retired implementation is preserved on
[`legacy/python-cli`](https://github.com/ai-engineers-guild/ai-stp/tree/legacy/python-cli).

## Boundaries

A setup belongs to one harness and pins immutable component versions. The CLI
validates the graph and assembles a bundle; the harness installation component
writes native configuration. Setup systems are integrated components with separate
repositories, acquired by the CLI. Harness executables are managed by their users
and vendors; ai-stp only observes the installed program.

Linux x86-64, Apple Silicon macOS and Windows x86-64 are exercised in CI. Isolated
setup installation and active-agent handoff currently work on Linux; the other
platforms explicitly refuse that boundary. `ai-stp capabilities --json` reports
what the running platform supports.

## Reference

- [Rust CLI](apps/cli/README.md): install, state, services and recovery.
- [Documentation](docs/index.md): machine contracts and server operations.
- [Development](CONTRIBUTING.md) and [working rules](AGENTS.md).
- [Desktop shell](apps/desktop/README.md): another client of the CLI contract.
- [Security reporting](SECURITY.md) and [code of conduct](CODE_OF_CONDUCT.md).

AGPL-3.0-or-later; see [LICENSE](LICENSE). User-published configurations and public
installation components retain their own licenses.
