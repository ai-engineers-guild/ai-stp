# Task runner

The [justfile](../justfile) owns local commands. Use `just --list` and
`just --show <recipe>` for the current inventory and dependency graph.
`docs_scripts/bootstrap_just.py` owns the tool pin; keep `minimum-version` aligned.

Recipe prefixes identify their owner: `docs`, `back`, `cli-v2`, `web`, `desktop`
and `infra`. `-gen` writes generated sources; `-static` checks drift; `-test`,
`-build` and `-regress` exercise the implementation; `-check` composes dependencies.
Keep executable logic in scripts and recipe bodies POSIX. Each recipe line runs
in a fresh shell. Document groups and arguments in recipe attributes.

CI executes the same commands directly. A new gate leaf needs both a workflow
command and an entry in `tests/contract/test_gate_split_covers_the_gate.py`.
Local-only formatting/hooks belong to `pre-commit`; network release evidence and
platform-specific infrastructure remain outside the aggregate gate. Read the
justfile for its current composition rather than duplicating it in prose.

Run `just --fmt --check` for recipe formatting and the affected recipe for behavior.
`test_quality_gate_policy.py` and `test_gate_split_covers_the_gate.py` enforce
shell conventions and local/CI parity.
