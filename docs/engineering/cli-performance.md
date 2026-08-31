---
description: "Measured CLI command costs, resolved bottlenecks, and budgets."
last_verified: "2026-08-29"
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

## Identified causes

### Importing the entire command registry

Three quarters of startup was spent on imports: `handler=version.run` requires
importing `version`, so thirty command modules loaded regardless of the command
entered. Descriptors now carry `"module:function"`, and the module is imported
at invocation time. `version` 0.870 → 0.545.

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

`tests/unit/test_cli_performance_regressions.py` contains three checks, and only
one concerns timing, because "runs concurrently" is a timing assertion. The
margin cannot overlap on any plausible machine: seven 0.1s detections take 0.7s
sequentially, while the boundary is 0.35s.

The other two check a property rather than duration: an index without digests
states that in a separate field, and `select eligibility` never calls `sha256`.
A budget in seconds fails on a busy runner and passes on a fast runner that has
regressed; such a check loses credibility by the third occurrence, and a check
that nobody runs protects nothing.
