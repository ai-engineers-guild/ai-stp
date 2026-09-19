# Provider and harness program

The provider manages native configuration; the harness program runs the coding
agent. The CLI owns provider acquisition. For an ordinary install, omit a
provider override so the CLI resolves a configured/managed provider or acquires
one automatically. Follow the installed version's declared source behavior;
newer CLI versions bootstrap their PyPI provenance verifier themselves.
Do not require the user to preinstall gh, Rust or a separate verifier for that path.

Do not type `ai-stp harness install` or `ai-stp harness status` for an ordinary
setup. The `install` intent acquires the program. Program presence, working
configuration and the vendor's own sign-in are separate results. Installation
does not require a model key for ai-stp.

Do not type `ai-stp provider fetch`. For explicit preload or repair resolve
`ai-stp provider trust`, `ai-stp provider check` and
`ai-stp provider conformance` from machine help. Preserve the returned
manifest and evidence; do not choose an executable by listing every file in
the download directory. A verified publisher and protocol conformance answer
different questions.

To update a provider do not type `ai-stp provider update plan`. Resolve that
family from machine help. Do not type `ai-stp harness update`. To update a
setup or the CLI itself use their respective playbooks. Provider replacement
alone never updates installed setups.

Do not type `ai-stp toolchain profile` or `ai-stp toolchain install` for an
ordinary setup. An optional missing tool does not justify a broad installation
unrelated to the requested setup.
