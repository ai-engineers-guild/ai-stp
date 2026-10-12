# Provider and harness program

The provider manages native configuration; the harness program runs the coding
agent. The CLI owns provider acquisition. For an ordinary install, omit a
provider override so the CLI resolves a configured/managed provider or acquires
one automatically. Follow the installed version's declared source behavior;
newer CLI versions bootstrap their PyPI provenance verifier themselves.
Do not require the user to preinstall gh, Rust or a separate verifier for that path.

Harness executables and their updates belong to the user and vendor. ai-stp
observes the installed version with `ai-stp toolchain harnesses`; it acquires
configuration providers, not harness distributions. The `install` intent
configures a setup. Program presence, working configuration and vendor sign-in
are separate results. ai-stp does not require a model key.

Do not type `ai-stp provider fetch`. For explicit preload or repair resolve
`ai-stp provider trust`, `ai-stp provider check` and
`ai-stp provider conformance` from machine help. Preserve the returned
manifest and evidence; do not choose an executable by listing every file in
the download directory. A verified publisher and protocol conformance answer
different questions.

To update a provider do not type `ai-stp provider update plan`. Resolve that
family from machine help. To update a
setup or the CLI itself use their respective playbooks. Provider replacement
alone never updates installed setups.

Do not type `ai-stp toolchain profile` or `ai-stp toolchain install` for an
ordinary setup. An optional missing tool does not justify a broad installation
unrelated to the requested setup.
