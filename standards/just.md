# `just` — the local command runner standard

`just` is the single entry point for local checks and generation. It is
deliberately **not** a CI dependency: workflows write the recipe bodies out
inline, and `tests/contract/test_gate_split_covers_the_gate.py` proves the
union of workflow commands covers the union of `just check` leaves. A check
cannot fall out of either side silently; this duality is load-bearing and
every rule below exists to preserve it.

## Version contract

- The pinned toolchain is `just 1.58.0`, distributed to developers by
  `docs_scripts/bootstrap_just.py` with a per-platform SHA256 table. Six
  platforms are pinned; an unlisted platform refuses rather than guessing.
- The justfile declares `set minimum-version := "1.58.0"`. The floor equals
  the pin: one number, one source of truth, a clear parse-time error instead
  of a feature silently mis-read by an older binary. Raise it only together
  with the bootstrap pin.
- `just --version` on a maintainer machine should match the pin. Package
  manager installs drift; the bootstrap is the canonical source.

## File structure

Fixed order, top to bottom:

1. Header comment — the contract of the file (gen/check duality, group
   taxonomy, the local-only boundary).
2. `set` directives — only the accepted ones, listed below.
3. Variables — shared command prefixes (`run`, `py`, `scripts`), tunables via
   `env_var_or_default`, gate snippets (`bunreq`, `uvreq`). `export` only the
   variables that must cross recipe lines (`COVERAGE_CORE`, `PYTHONUTF8`).
4. `default` — lists recipes, never runs work.
5. Gate aggregates — `setup`, `gen`, `check`, `pre-commit`.
6. Group sections, each under a `# --- <group> ---` rule, in the order
   `docs`, `back`, `web`. `infra-*` recipes follow web (Docker, Compose,
   host deploy). They are a group, but they are not in `check`. Ungrouped
   concerns (release, evidence, safety) come last.

## Naming taxonomy

A recipe's group is its owner and its prefix is mandatory:

| Prefix | Owns |
| --- | --- |
| `docs-*` | documentation basis — specs, ADRs, `docs/`, MkDocs |
| `back-*` | Python — `packages/`, `apps/api`, `apps/platform`, `apps/cli`, `tests/` |
| `web-*` | `apps/web` |
| `infra-*` | Docker images, Compose stacks, host-side deploy chain — **not** in `just check` |

Every group carries the same verb set, so a command is derived, not
memorized:

| Verb | Meaning |
| --- | --- |
| `-gen` | writes machine text (format, generated artifacts) |
| `-static` | reads source without executing it |
| `-test` | runs tests |
| `-build` | produces an artifact |
| `-regress` | runs the built artifact in a real engine |
| `-check` | the group's aggregate |

Recipes outside those prefixes name a domain directly: `evidence-*`
(deployed/released proof, never in the gate), `safety-*`, `public-*`,
`release-*`, `estate-*`.

## Rules

1. **`-check` never writes.** Generated/source drift is caught in `-static`
   and repaired by an explicit `-gen` call. A check that fixes what it
   measures has stopped measuring.
2. **Aggregates delegate; they do not duplicate.** A `-check` recipe lists
   dependencies only. `just` runs each recipe once — the same build in two
   bodies is paid every run (measured: 45 s locally, ~90 s on the fleet
   class, when `web-regress` repeated `web-build`'s body).
3. **The justfile is an index, not a script host.** Logic lives in real
   files — `docs_scripts/`, `release_scripts/`, `.github/scripts/` — which CI
   can call without `just` and which have their own tests and shell dialect.
   Recipe bodies stay POSIX one-liners. Shebang/`[script]` recipes are
   rejected by convention: they would hide the script from the parity test
   and from review.
4. **Each recipe line is a fresh shell.** `cd`, variable assignments and
   multi-command steps must live on one logical line (`cd apps/web && bun
   run lint`), or use `\` continuations. A variable set on one line is gone
   on the next.
5. **Tool-version gates fail loudly.** `bunreq`/`uvreq`-style snippets exit 1
   on absence or drift — a missing tool fails the recipe, never skips the
   step. bun rewrites `bun.lock` in its own line's format; uv stamps its
   version into `dist-info/WHEEL`, so "close enough" costs a real incident
   both times.
6. **Tunables are env vars with defaults and a reason.** Pattern:
   `env_var_or_default("AI_STP_*", "...")` plus a comment naming the fleet
   shape or measurement that chose the default (`AI_STP_TEST_WORKERS`,
   `AI_STP_TEST_DIST`, `AI_STP_TEST_COVERAGE_CORE`). `auto`-style host
   probing is rejected for gate defaults: a 12-core laptop is not the 4-vCPU
   fleet class the gate is shaped for.
7. **Every recipe gets `[group('…')]`** matching its section, so
   `just --list` renders the taxonomy instead of a flat wall of 60+ names.
   Groups: `gate`, `docs`, `back`, `web`, `release`, `evidence`, `safety`,
   `misc`.
8. **Every parameter gets `[arg(name, help="…")]`** — parameters are the
   recipe's interface and `--show`/usage output should say what each one is.
9. **Pass-through args use `*args` + `{{args}}` interpolation**, not
   `[positional-arguments]` + `"$@"`. The contract is word-splitting:
   `just back-test-fast -k foo` and `just back-test-fast "-x -k foo"` both
   reach pytest as flags. `"$@"` preserves each CLI argument as one word,
   which breaks the quoted-multi-flag form callers actually use. Data that
   must survive spaces never travels through `*args` — give it a named
   parameter.
10. **Private helpers get `[private]`.** A recipe that exists only as a
    dependency of another is marked private so `--list` shows the public
    surface. `just-fmt` is the example.
11. **Recipes keep `#` doc comments** — they render in `just --list` and are
    the recipe's documentation. English only (repository rule). The list takes
    the *last* contiguous comment line as the recipe's summary, so a
    multi-paragraph why-comment ends in a fragment there; give such recipes a
    `[doc('…')]` one-liner, which overrides the comment for the listing while
    the prose stays.
12. **Comments in recipe bodies** (`# …` on an indented line) are allowed
    for why-notes at the point of execution; the shell reads them as
    comments harmlessly.
13. **Dangerous-looking operations stay callable.** No `[confirm]`: recipes
    are run by agents non-interactively, and the publish path is already
    gated by the manifest, explicit arguments and review. Friction that
    blocks automation is not a control.
14. **`just --fmt` is the canonical format** and is enforced in the local
    `pre-commit` recipe via `just-fmt`. It cannot live in `check`: CI runs
    no `just` (rule 15). `--fmt` also owns attribute ordering — it rewrites
    attributes into its own order, so hand-arranged attribute sequences are
    churn the formatter will undo.
15. **The `check` tree must not invoke `just`.** Every leaf of `check` needs
    a `_LEAF_TOKENS` entry and the command must appear in a workflow —
    `just --anything` can satisfy neither. Local-only checks (this file's
    own format, hooks) hang off `pre-commit`, which the parity test does
    not expand.

## Accepted and rejected features

| Feature | Verdict | Reason |
| --- | --- | --- |
| `set minimum-version` | **use** — pinned to the toolchain | parse-time floor; one version contract |
| `set shell` | **reject** — keep default `sh -cu` | recipe bodies are POSIX; Windows resolves Git-bash `sh`, and CI parity requires no bash (`test_quality_gate_policy.py`) |
| `set windows-shell` | **reject** | same as above; `run_bash.py` owns the Windows bash problem where bash is genuinely needed |
| `set dotenv-load` | **reject** | `.env` holds secrets; auto-loading them into every recipe's environment turns a recipe echo into a leak |
| `set export` | **reject** | blanket-exporting every variable hides which ones recipes actually need; `export` stays per-variable |
| `set fallback` | **reject** | an unknown recipe would dispatch into a parent directory's justfile — surprising across repo boundaries |
| `set quiet` | **reject** | the echoed command line is the audit trail in local logs |
| `set unstable`, `[cache]` | **reject** | unstable features in a published file break on the next downgrade; the gate does not cache |
| `set positional-arguments` | **reject globally**; per-recipe only where word-preservation is the contract | see rule 9 — pass-through wants word-splitting |
| `set ignore-comments` | **allowed, unused** | body comments are already harmless; enabling it is churn without a failure it prevents |
| `set working-directory` | **reject** | recipes rely on just's default cd-to-justfile; a different root would move every relative path |
| `[group]` | **required** on every recipe | `--list` renders the taxonomy |
| `[arg]` | **required** on every parameter | parameter documentation in usage output; `pattern=` only where the format is truly closed |
| `[private]` | **required** on dependency-only recipes | `--list` shows the public surface |
| `[doc]` | **allowed**; doc comments preferred | comments are the established form and render identically |
| `[confirm]` | **reject** | agents run recipes non-interactively; see rule 13 |
| `[no-cd]` | **allowed** where a recipe genuinely works from the caller's cwd | none currently need it |
| `[script]`/`[shell]`/shebang recipes | **reject** | logic belongs in script files (rule 3) |
| `[linux]`/`[macos]`/`[windows]`/`[unix]` | **allowed** for OS-gated recipes | a recipe that cannot run on an OS should say so rather than fail inside |
| `[env]` | **allowed** for recipe-scoped env | prefer it over exporting globally |
| `[parallel]` | **reject** | dependency order in aggregates is deliberate (e.g. `web-build` before `web-static` for `tsconfig`); parallel would reorder measured sequences |
| `[metadata]`/`[timestamp]` | **allowed** | diagnostics only, no behavior change |
| `mod` / `import` | **reject in this file** | modules change invocation (`just back static` ≠ `back-static`) and the parity parser reads one flat file; a future justfile that starts modular may revisit this |
| Conditional `if`/`else`, `prepend`, `env_var_or_default` | **use** | already load-bearing; keep expressions small and commented |

## Verification

| Check | Where it runs | What it proves |
| --- | --- | --- |
| `just --fmt --check` | `pre-commit` → `just-fmt` (local only) | canonical formatting |
| `just --summary` / `--list` | manual / this standard's review | file parses on the pinned version |
| `test_gate_split_covers_the_gate.py` | `just back-test`, CI `contract` shard | `check` leaves ⇄ workflow commands, no `just` in CI |
| `test_quality_gate_policy.py` | same | recipes stay POSIX (no bash), no `sudo`, dry-run expansion works |
| `test_coverage_gate.py` | same | `COVERAGE_CORE` pin and coverage recipe shape |
| `test_bootstrap_just.py` | same | pin table resolves every supported platform, retries and checksums behave |
| `public_export --report` (`back-static`) | gate | every tracked root is named in the manifest — `standards/` is withheld |

## Adding or changing a recipe — checklist

1. Name it `<group>-<verb>` or give it a domain prefix; add `[group]`.
2. Parameters get `[arg(help=…)]`; pass-through tails get `*args` + `{{args}}`.
3. Keep the body POSIX, one logical line per step; push real logic into a
   script file.
4. If it belongs in `check`: add its command tokens to `_LEAF_TOKENS` in
   `test_gate_split_covers_the_gate.py` **and** the command itself to the
   workflow — the parity test fails on either half alone.
5. If it is local-only, hang it off `pre-commit` or leave it standalone —
   never inside the `check` tree.
6. Run `just --fmt`, then `just <recipe>` once for real.
7. English comments that say *why*, naming the measurement or incident
   where one exists.
