# Contributing

## Before you begin

Read [AGENTS.md](AGENTS.md), the code and current contract for the area you are
changing, and [the Git workflow](docs/engineering/git-workflow.md). Consult
applicable specifications and ADRs when the task concerns their boundary.
The [implementation roadmap](docs/engineering/implementation-roadmap.md) owns
the remaining work; linked GitHub issues carry current checkpoint evidence.

## Development on a new workstation

Clone the canonical repository and start from the integration branch:

```bash
git clone https://github.com/ai-engineers-guild/ai-stp.git
cd ai-stp
git switch --track origin/dev
git switch -c feat/57-next-native-slice
```

Use the tool versions selected by [.github/workflows/check.yml](.github/workflows/check.yml),
[.uv-version](.uv-version) and [.bun-version](.bun-version). Install Rust through
rustup; [apps/cli-v2/rust-toolchain.toml](apps/cli-v2/rust-toolchain.toml) selects
the native toolchain. The native README describes the C compiler and libclang
prerequisites. [docs_scripts/bootstrap_just.py](docs_scripts/bootstrap_just.py)
can install the pinned `just` into a user-owned `JUST_INSTALL_DIR` on PATH.

For native CLI work, prepare the Python contract oracle and run the native gate:

```bash
just setup-python
just cli-v2-check
```

`just setup` additionally prepares documentation and web dependencies when
those areas are needed. Follow AGENTS.md for checks affected by each change.
Keep lockfiles unchanged during setup. Rebuild local dependencies and caches;
do not copy another workstation's virtual environment or target directories.

Continue the Rust program from [#57](https://github.com/ai-engineers-guild/ai-stp/issues/57),
the roadmap and [the native contract](apps/cli-v2/README.md). A published preview
does not transfer production state ownership. Existing device credentials and
owner state are not development inputs: authenticate the new workstation
through the normal account flow when a connected task requires it.

Setup-component changes start in their maintained authoring repository and
follow its AGENTS.md; the seven public trees are generated outputs. The ai-stp
repository alone is sufficient for native CLI development against published
components. Session transcripts, local agent memories and temporary receipts
are not prerequisites for resuming work.

## Change rule

Follow the source-of-truth and change rules in AGENTS.md. Implement within
existing contracts directly. When a boundary changes, record an ADR if the
architecture rule changes, implement and verify the behavior, then reconcile
its active specification and affected documentation with the code.

## Pull request

A PR must be narrow in its primary purpose and include the exact base/head, affected specifications and ADRs, contract and schema changes, commands run and their results, checks not run, migration, rollback, cross-repository order, and residual risks.

Do not weaken checks or update golden output without semantic analysis.

### Golden fixtures

`tests/golden/cli/machine-help.json` pins the `help --agent` registry — the
machine boundary seven harness projections read. When a command is added,
renamed, or re-described, regenerate it rather than editing by hand:

```bash
uv run python - <<'PY'
import json
from pathlib import Path
from ai_stp_cli.commands import machine_help

data = machine_help.registry({}).payload.model_dump(mode="json")
data["cli_version"] = "0.0.0-pinned"
Path("tests/golden/cli/machine-help.json").write_text(
    json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
PY
```

Review the diff: it is the reviewed record of a machine-contract change.

## External actions

The user's task defines authorization. Follow AGENTS.md for publication,
deployment, irreversible data deletion and access changes; a task already
authorizing an action does not require another confirmation for each step.
