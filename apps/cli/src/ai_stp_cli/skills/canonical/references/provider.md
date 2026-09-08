# Provider and harness program

The provider manages native configuration; the harness program runs the coding
agent. The CLI owns provider acquisition. For an ordinary install, omit a
provider override so the CLI resolves a configured/managed provider or acquires
one automatically. Follow the installed version's declared source behavior;
newer CLI versions bootstrap their PyPI provenance verifier themselves.
Do not require the user to preinstall gh, Rust or a separate verifier for that path.

Use `ai-stp harness install` to install the program into an explicit prefix,
with the intended configuration target kept separate. Verify with
`ai-stp harness status`. Program presence, working configuration and the
vendor's own sign-in are separate results. Continue the setup procedure after
program installation; installation does not require a model key for ai-stp.

For explicit preload or repair resolve `ai-stp provider fetch`,
`ai-stp provider trust`, `ai-stp provider check` and
`ai-stp provider conformance`. Preserve the returned manifest and evidence;
do not choose an executable by listing every file in the download directory.
A verified publisher and protocol conformance answer different questions.

To update a provider use `ai-stp provider update plan` and its returned apply
route. To update a program use `ai-stp harness update`; to update a setup or
the CLI itself use their respective playbooks. Provider replacement alone
never updates installed setups.

Use `ai-stp toolchain profile` and `ai-stp toolchain install` only for actual
requirements of the selected environment. An optional missing tool does not
justify a broad installation unrelated to the requested setup.
