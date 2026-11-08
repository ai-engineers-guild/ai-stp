# Task runner

The [justfile](../justfile) owns project commands. Use `just --list` and
`just --show <recipe>` for the current inventory and dependency graph.
`docs_scripts/bootstrap_just.py` owns the tool pin; keep `minimum-version` aligned.

Recipe prefixes identify their owner: `docs`, `back`, `cli`, `web`, `desktop`
and `infra`. `-gen` writes generated sources; `-source` needs no build;
`-static` also includes compiled analysis; `-test`,
`-build` and `-regress` exercise the implementation; `-check` composes dependencies.
Keep executable logic in scripts and recipe bodies POSIX. Each recipe line runs
in a fresh shell. Document groups and arguments in recipe attributes.

`just setup` explicitly installs dependencies. `just check` runs offline source
checks without installing, compiling or testing. `just fix` applies formatting;
`just test` runs test suites and compiled analysis; `just build` produces
artifacts; `just verify` composes full verification. Git hooks run source checks.
Builds and tests belong on execution hosts with the required native SDKs.

CI currently shards the underlying commands directly. A new verification leaf
needs both a workflow command and an entry in
`tests/contract/test_gate_split_covers_the_gate.py`. Network release evidence and
platform-specific infrastructure have their own jobs. Read the justfile for the
current composition.

Run `just --fmt --check` for recipe formatting and the affected recipe for behavior.
[Gate coverage tests](../tests/contract/test_gate_split_covers_the_gate.py) enforce
local/CI recipe coverage. The owning formatters and linters check source syntax.
