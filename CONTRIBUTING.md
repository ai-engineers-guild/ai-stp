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

## Validation and integration

Run affected checks listed in AGENTS.md. `just --list` describes recipes and
`just --show check` gives the aggregate. For local Mermaid rendering an installed
Chrome can be selected with `PUPPETEER_EXECUTABLE_PATH`.

Keep lockfiles pinned. Regenerate changed schemas or projections through their
own recipe and review the diff. Behavioral tests and machine schemas own contracts;
prose should explain usage rather than duplicate command/field inventories.

Follow the [Git workflow](docs/engineering/git-workflow.md). Include the problem,
resulting behavior, tested commit and recovery path in the PR. Native configuration
changes belong in this repository. Preserve published external-provider artifacts
and regenerate projections through their source recipe.

For documentation changes, run `just docs-gen` after updating index metadata and
`just docs-check` to validate the engineering site and both user locales.
