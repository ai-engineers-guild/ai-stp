---
description: "Measured CLI command costs, resolved bottlenecks, and budgets."
last_verified: "2026-10-07"
---

# CLI Performance

The requirements owner is `#453`. This document records what was measured, the
evidence for it, and the resulting budgets. The numbers are not a goal in
themselves: none of the changes below removed a check.

## How to measure

```bash
uv run ai-stp <command>   # 7 repetitions, min / p50 / max
```

Profile the command internals separately:

```bash
uv run python -c "import cProfile, runpy, sys; sys.argv=['ai-stp', ...]; \
  cProfile.run('runpy.run_module(\"ai_stp_cli\", run_name=\"__main__\")', sort='cumulative')"
```

Measure the network and provider separately from local startup: a slow external
service masks a regression in the CLI itself rather than revealing it.

## Measurement

Linux, Python 3.14.6, `uv run`, a repository of 4,359 files, p50 from 7 repetitions.

| command | before | after |
|---|---|---|
| `version` | 0.870 | 0.545 |
| `help --agent --json` | — | 0.578 |
| `config show --json` | — | 0.563 |
| `doctor --json` | — | 0.771 |
| `toolchain harnesses --json` | 2.293 | **1.306** |
| `component discover --json` | — | 0.683 |
| `component search --json` | — | 0.552 |
| `select eligibility --json` | 2.616 | **1.379** |
| `target status --json` | — | 0.557 |

The floor is about 0.545s: `uv run` plus imports. Anything close to it is bound
by interpreter startup, not command execution.

Second measurement, 2026-10-04: Linux, Python 3.14.7, the workspace entry point
(`.venv/bin/ai-stp`, no `uv run`), CPU time averaged over five runs.

| command | before | after |
|---|---|---|
| `version --json` | 4.21 | **0.41** |
| `contract inventory --json` | ≈4.2 | **0.41** |
| `capabilities --json` | — | 0.39 |
| `help --agent` | — | 0.40 |

Third measurement, 2026-10-05: the published wheels `ai-stp-cli` 0.0.38 and
0.0.39, each installed by `uv pip install` into its own fresh environment, run
as whole processes on a Linux workstation with eight cores under load of about
three. User CPU in seconds, median of five runs:

| command | 0.0.38 | 0.0.39 |
|---|---|---|
| `version --json` | 4.51 | **1.55** |
| `contract inventory --json` | 4.30 | **1.58** |
| `capabilities --json` | 1.67 | 1.60 |
| `help --agent` | 1.64 | 1.46 |

The recorded digest removes about three seconds, as the second measurement
found, but the 0.39–0.41 it reported did not reproduce: every command now rests
on a floor of about 1.5s, almost all of it imports. `python -X importtime`
attributes 1.28s to importing `ai_stp_cli.__main__`, of which about 0.9s is
`ai_stp_contracts.machine_help` and the eagerly importing `ai_stp_contracts`
package — pulled in by `ai_stp_cli.config` and `ai_stp_cli.errors` before any
command runs. Moving one annotation-only import behind `TYPE_CHECKING` does not
help while `config` imports the module directly. Lowering the floor means
loading the contract models a command actually uses, not the whole package;
until then the whole-process cost of a local read-only command is above the
0.8s budget below on this workstation.

Fourth measurement, 2026-10-05, after two changes to what every invocation
imports. Both trees are workspace environments on the same Linux workstation
(load average 5–8), interleaved, user CPU in seconds, median of seven runs:

| command | before | after |
|---|---|---|
| `version --json` | 1.75 | **1.13** |
| `contract inventory --json` | 1.80 | **1.17** |
| `capabilities --json` | 1.82 | **1.16** |
| `help --agent` | 1.80 | **1.29** |

- Every contract model inherits `ContractModel`, which sets Pydantic's
  `defer_build`: a model builds its validator and serializer the first time it
  validates or serializes. Of the 483 contract models the CLI imports, only the
  four the command registry instantiates are built by the import. Importing
  `ai_stp_cli.app` fell from about 1.26s to 0.72s.
- The heartbeat and update-notice checks that end every command imported httpx
  at module level, about 0.05s each time; the network code now imports it when
  a heartbeat is due or the update cache has expired.

The remaining floor is mostly field collection for the models themselves —
`ai_stp_contracts.machine_help` alone defines 194 classes — and is still above
the 0.8s budget below. Lowering it further means splitting the machine-help
module so a command imports only the models it returns.

Fifth measurement, 2026-10-05, after the contract package stopped importing
what a command does not use. Same method as the fourth, both trees interleaved,
load average 4–7:

| command | before | after |
|---|---|---|
| `version --json` | 1.10 | **0.70** |
| `contract inventory --json` | 1.13 | **0.71** |
| `capabilities --json` | 1.10 | **0.74** |
| `help --agent` | 1.11 | **0.74** |
| `config show --json` | 1.01 | **0.64** |
| `doctor --json` | 1.22 | **1.06** |

- `ai_stp_contracts.machine_help` is split into `ai_stp_contracts.cli`, sixteen
  modules by command family, and the CLI imports the family it uses.
  `machine_help` re-exports all 215 names for the schema generator, the
  platform and the tests; the generated schemas did not change by a byte.
- The package root loads its 139 re-exported names on first use through a
  module `__getattr__`. Before, any `ai_stp_contracts.<module>` import first
  imported auth, catalog, context, corporate, health, http and identity.
- The command router read the shipped intent names from `application.inspect`,
  which imports the doctor checks and the task-intent models; the names now
  live in `application.inventory`, and `capabilities` is built in its own module
  for the same reason.

Every local read-only command is now within the 0.8s budget; `doctor` asks the
harness programs for their versions and belongs to the 1.5s class. What every
invocation still imports beyond pydantic, click and the foundation: the
passports package root, which loads markdown-it for the three constants the
registry needs (about 0.05s), and the heartbeat contract that the end-of-command
check imports with the corporate contract behind it (about 0.06s).

At the fifth measurement the desktop sidecar added its own cost: PyInstaller `--onefile`
unpacks the archive on every call. On the same workstation a `--onedir` freeze
of the same CLI answered `version --json` in 2.6s against 3.1s for `--onefile`
(median of five, wall clock); the required change of bundle layout
was recorded in the roadmap rather than made in that wave. The sidecar ran
the same imports, so the fifth measurement lowered its per-call cost as well.

## Desktop directory packaging — October 7

The shell now bundles the complete PyInstaller `--onedir` tree through Tauri
resources (ADR-0222), with no extraction on each invocation. A control freeze
used the earlier onefile script against the same CLI 0.0.42 source and locked
dependency closure. After one warm-up per binary, seven alternating
`version --json` calls used the same temporary home on this Linux workstation.
Wall-clock medians were **3.133 s onefile → 2.223 s onedir** (29% lower).
The host was concurrently building packages: ranges were 2.082–5.972 s and
1.313–5.763 s, respectively. This is a loaded-host packaging comparison, not
a portable latency promise or a replacement for the CLI user-CPU budgets.

Control executable SHA-256:
`49c384eea1978b2775068e920191c597a707082a2b0d28d4842dc06c8a769e15`.
The local deb containing the onedir tree has SHA-256
`e92fa670eb0b2254a84763b4be26f4ee7e4bc1cec1fc54e0dd4127d7a9335870`.
Its extracted resource tree passed the app's filtered-environment runner
probe. These are audit artifacts, not published desktop 0.0.7 release bytes;
the new layout is prepared for desktop 0.0.8.

## Identified causes

### Importing the entire command registry

Three quarters of startup was spent on imports: `handler=version.run` requires
importing `version`, so thirty command modules loaded regardless of the command
entered. Descriptors now carry `"module:function"`, and the module is imported
at invocation time. `version` 0.870 → 0.545.

### Rendering every schema to report one digest

`version` and `contract inventory` report the contract digest of the standard
inventory (`SPEC-060`). The digest binds the JSON Schema body of every exported
model, so computing it rendered and canonicalised about five hundred schemas on
every call: 4.2s of CPU for the command an agent or the desktop shell runs
first. The digest is a property of the source, not of the call. The generator
writes it to `ai_stp_contracts/standard_inventory.json`
(`python -m ai_stp_contracts.inventory_record`, part of `just back-gen`), the
commands read that record, and `back-static` refuses a record that differs
from the models. `version` 4.21 → 0.41.

### Seven sequential subprocesses

`detect_all` queried `--version` from seven harnesses sequentially: for 1.74s of
2.29s the process was in `poll`. The requests are independent and read-only, so
they now run concurrently. `ThreadPoolExecutor.map` returns results in **input**
order, not completion order, so the response remains the same tuple as before.

Measured by harness: `cursor` 0.633s, `opencode` 0.610s, `pi` 0.295s,
`antigravity` 0.103s, `grok-build` 0.030s, `codex` 0.008s, `claude-code`
0.009s. Total 1.688s, concurrent 0.700s. The remainder is another program's
startup time; it cannot be accelerated here, only stopped from queuing.

### A symbol survey answering an already answered question

`select eligibility` built `symbols.survey`—1.16s of 2.9s—to obtain the list of
project languages. The survey is **given** `(path, language)` from the index, and
`_summarised` groups everything it receives, readable or not; therefore, the
languages it returns are the languages it was given.

Not quite, which exposes a second defect: the survey stops at
`MAX_OUTLINED_FILES` (2000) and reports only languages before the cutoff. A
project whose Go files all sort after the first two thousand lost
`project.language.go` from its capabilities, and Go components were rejected for
lacking a capability that existed. Reading the index directly is both cheaper
and complete.

### Hashing files that nobody reads

`project_index.build` reads and hashes every file. Measured on 4,080 files:
reading 0.29s, SHA-256 0.91s—the hash accounts for three quarters of the scan.
`select eligibility` reads no digest: it needs names, languages, and the presence
of `.git`.

`build(root, digests=False)` was added: the same scan, classification,
exclusions, and binary check, with only hashing skipped. `Index.digested` tells
the reader which case applies, so `digest is None` does not mean both "too
large" and "not requested."

## Considered and not implemented

`projects.contains(base, place)` resolves **both** sides for every file even
though `base` is constant during the scan: 8,711 `realpath` calls for 4,359
files, 0.267s. Half are redundant.

Intentionally left unchanged. This check rejects a symlink outside the tree, and
the gain is about 0.13s, one tenth of the command. Rule `#453` is explicit here:
do not weaken checks for a number. This record prevents the next reader from
measuring it again.

## Budgets

Derived from measurement, not preference:

- local read-only command without a tree scan: **up to 0.8s** p50;
- command scanning a project: **up to 1.6s** p50 on a tree of about 4,000 files;
- command querying external programs: **up to 1.5s** p50, where the CLI itself
  is responsible for the difference from the slowest program's time.

The network and provider are outside these budgets and are measured separately.

## Regression checks

`tests/unit/test_cli_performance_regressions.py` contains nine checks, and only
one concerns timing, because "runs concurrently" is a timing assertion. The
margin cannot overlap on any plausible machine: seven 0.1s detections take 0.7s
sequentially, while the boundary is 0.35s.

The other eight check a property rather than duration: an index without digests
states that in a separate field, `select eligibility` never calls `sha256`,
`version` / `contract inventory` never import the schema generator, every
contract model defers its build, a local command never imports httpx, an
agent's first probes (`version`, `capabilities`, `help --agent`, `config show`)
load only the `ai_stp_contracts.cli` families they use, the package root's
three export lists agree, and `machine_help` re-exports every family name.
A budget in seconds fails on a busy runner and passes on a fast runner that has
regressed; such a check loses credibility by the third occurrence, and a check
that nobody runs protects nothing.
