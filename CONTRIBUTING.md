# Contributing

## Before you begin

Read:

1. `AGENTS.md`;
2. the applicable active specification;
3. the architecture documents for the relevant area;
4. the relevant ADRs;
5. `docs/engineering/git-workflow.md`.

## Change rule

Observable behavior does not begin with code. First record the objective, boundaries, requirements, errors and partial states, security, compatibility, and acceptance criteria.

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

Push, PR, release, provider promotion, deployment, data deletion, and credential changes are performed only after explicit authorization.
