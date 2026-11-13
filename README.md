# ai-stp

[Русский](README.ru.md) · [Catalog](https://ai-stp.aiguild.space) ·
[User docs](https://docs.nddev.asia/en/)

ai-stp is a Rust CLI that creates and installs exact configurations for AI
harnesses. Each setup pins immutable component versions for one harness. The web
provides accounts and the public catalog. The CLI and Desktop use the same engine.

## Start

Follow the [CLI installation guide](apps/cli/README.md#install-and-update) to
verify and install an archive or use a package manager. For a new local state:

```sh
ai-stp init --credential-store os_keyring --json
ai-stp help --agent --json
```

Use the [state migration procedure](apps/cli/README.md#state-and-first-run) for
an existing Python registry. Local configuration needs no account or model key.

Native configuration and process handoff are tested on Linux x86-64, Apple
Silicon macOS and Windows x86-64. Use `ai-stp capabilities --json` to check
`native_configuration` on your executable. The user or vendor manages the
harness program.

[Desktop](apps/desktop/README.md) · [Engineering and operations](docs/index.md) ·
[Development](CONTRIBUTING.md) · [Security](SECURITY.md) ·
[Code of conduct](CODE_OF_CONDUCT.md)

## Credit

Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Published configurations
retain their own licenses, and releases before the change keep their original terms.
Please credit NDDev and link
[this repository](https://github.com/ai-engineers-guild/ai-stp).
