# Development

Read [AGENTS.md](AGENTS.md). The [Rust CLI guide](apps/cli/README.md) owns current
CLI behavior; the executable command registry owns parameters. Work is tracked
in GitHub issues and PRs, not in a second set of requirements or plans.

## Development on a new workstation

```sh
git clone https://github.com/ai-engineers-guild/ai-stp.git
cd ai-stp
git switch --track origin/dev
git switch -c feat/your-change
just setup-python
just cli-check
```

Use tool versions from `.uv-version`, `.node-version`, `.bun-version`, the native
`rust-toolchain.toml` and `.github/workflows/source.yml`. The native guide lists
C compiler/libclang prerequisites. `docs_scripts/bootstrap_just.py` installs the
pinned task runner into a user-owned `JUST_INSTALL_DIR` on PATH.

`just setup` also prepares documentation and web dependencies. Regenerate caches
and environments locally; do not copy them from another workstation. Existing
account state is not a development fixture: sign in normally on a new device.

`just setup-python-source` prepares Python and the small root Bun tool set for
source analysis. The official basedpyright CLI runs on the selected Node SDK;
runtime-only Python jobs use `just setup-python`. Checks consume prepared
dependencies and never install them.

Markdown and YAML source checks use native Rumdl and Ryl from the workstation SDK.
CI prepares their exact assets from `.github/documentation-check-tools.json`.
`just docs-static` needs no Mermaid installation; rendering still uses
`just setup-docs` and the frozen documentation lock.

`just infra-source` checks GitHub workflows, Dockerfiles and all tracked shell
scripts with Actionlint, Hadolint and ShellCheck. It runs in `just check` without
Docker; CI prepares exact assets from `.github/infra-check-tools.json`.
`just infra-static` adds every supported Docker Compose configuration.

The disposable CI source-secret owner uses a pinned Betterleaks executable with
explicit `.betterleaks.toml`, redacted reports and live credential validation
disabled. Its fixtures verify exact exemptions, changed-line/path refusal and
Bun lockfile coverage before scanning the source tree and PR commits.
Tests and generated contracts stay in scope. Public examples use exact rule,
path and line conditions, verified with changed-credential and outside-path
controls.

Native suites use cargo-nextest; doctests remain a separate Cargo step. Hosted CI
prepares exact tool assets from `.github/nextest-*.json` and
`.github/rust-check-tools.json`. Native workstations need those versions through
their existing SDK provider. `just setup-rust-analysis` prepares locked crate
sources before the offline `just rust-dependencies` checks. This separate recipe
checks dependency use, version constraints and sources; the all-lock security
scan and distribution-license review keep their existing owners.

## Validation and integration

Run affected checks listed in AGENTS.md. `just --list` describes recipes and
`just --show check` gives the aggregate. For local Mermaid rendering an installed
Chrome can be selected with `PUPPETEER_EXECUTABLE_PATH`.
For web browser checks, `PLAYWRIGHT_CHROME_CHANNEL=chrome-beta` selects an
already provisioned Google Chrome Beta; the default is `chrome`. Checks launch
an isolated profile, report the actual version and never install a browser.

Keep lockfiles pinned. Regenerate changed schemas or projections through their
own recipe and review the diff. Behavioral tests and machine schemas own contracts;
prose should explain usage rather than duplicate command/field inventories.

Follow the [Git workflow](docs/engineering/git-workflow.md). Include the problem,
resulting behavior, tested commit and recovery path in the PR. Native configuration
changes belong in this repository. Preserve published external-provider artifacts
and regenerate projections through their source recipe.

For documentation changes, run `just docs-gen` after updating index metadata and
`just docs-check` to validate the engineering site and both user locales.
