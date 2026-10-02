# Development quickstart

## Current status

Work status is tracked in `docs/engineering/implementation-roadmap.md`. The `uv` workspace materializes the shared packages (`foundation`, `passports`, `assurance`, `contracts`, `sources`) and the applications (`cli`, `api`, `platform`, `worker`); `apps/web` is a Node/bun workspace outside `uv`. Per-file schemas and `openapi.json` are generated in `schemas/v1`. Remaining work is tracked in GitHub issues.

Useful facts about `apps/cli`: the command is installed as `ai-stp`; `uv run ai-stp task intents --json` is the agent bootstrap; `uv run ai-stp doctor --json` reports installation state when asked what is broken; `uv run ai-stp device init --json` creates this device's identity; `uv run ai-stp device show --json` shows it and the key location without creating anything; `uv run ai-stp passport developer init --json` creates the local registry and developer passport; and `uv run ai-stp auth status --json` shows the installation's relationship to the platform: `local_only`, `authenticated`, `expired`, or `revoked`. Expert `help --agent --json` is the full command registry — do not type `ai-stp capabilities` as the first move. Each command is declared exactly once: the parser is built from the registry and machine help is rendered from the same source, so they cannot diverge. See `docs/agent/machine-help.md` for details.

Useful facts about `packages/contracts`: it carries the frozen `/v1` boundary together with a shared fixture corpus, mock transport, and conformance suite. The mock requires `httpx` and is provided through the optional `ai-stp-contracts[mock]` dependency. See `docs/contracts/fixture-corpus.md` for details.

The sole source of truth for Python dependencies is the root `uv.lock`; documentation tools live in the `docs` group and development tools in the `dev` group. Node tools are pinned in `docs_scripts/bun.lock` and installed with the `bun` version from `.bun-version`; recipes check it exactly because `bun install` from another release line rewrites the lockfile into a format the gate cannot read. Arbitrary global linter versions are not used.

## Installing the CLI

```bash
uv tool install ai-stp-cli
ai-stp task intents --json
```

This is the same command promised by the landing page, and the release gate verifies the full path: `just release-candidate` builds the wheel, and `just release-candidate-install` installs it into an isolated tool directory, executes it outside the source tree, and removes it. Administrator privileges are not required.

Uninstallation removes only the CLI files:

```bash
uv tool uninstall ai-stp-cli
```

Local data—the registry, passports, device identity, and cache—remain in `${XDG_DATA_HOME}/ai-stp`. Removing them is a separate explicit user action, not a side effect of uninstalling the program.

## Requirements

- Python 3.12 or 3.14;
- `uv` 0.12.19 or later (the gate pins `.uv-version`);
- `just` — the recipe runner every command below goes through;
- `bun` matching `.bun-version` (1.4.2) — recipes check it exactly because
  `bun install` from another release line rewrites the lockfile into a format
  the gate cannot read;
- Node.js 24 — `web-regress` serves the standalone build through
  `node .next/standalone/server.js`;
- Git.

For `web-regress`, the suite drives the stable Chrome already on the machine
(`channel: "chrome"`); `ensure-chrome.sh` downloads a pinned Chrome into the
user's Playwright cache only as the fallback when none is found. Every current
CI runner image ships Chrome; the project never invokes `sudo`, and system
preparation of the machine is not part of `just check`.

Provider protocol v3 on Linux uses the system `bwrap` only after a runtime
capability probe. Command presence is insufficient: the test requires a positive
control of local DNS-UDP/IPv4/IPv6 endpoints and proof that they are unavailable
inside the network namespace. `ai-stp provider network --json` reports the v3
local phase for this machine as exactly one of: `network_denied` (launcher
proven), `unisolated_by_trust` (Windows only, and only with the explicit trust
reasons), or `refused` — no launcher and no trust basis, which is the answer on
macOS and on a Linux host without `bwrap`. Refusal is fail-closed: the phase is
denied before the provider starts rather than run unisolated.

Observable result for the current machine:

```bash
uv run ai-stp provider network --json
```

## Setup and validation

```bash
just setup
just gen
just check
```

The entire `justfile` uses two verbs: `gen` writes and `check` reads. `just gen` regenerates all machine artifacts—documentation tables of contents, `schemas/v1`, Skill projections, the typed web client, and source formatting; always review the resulting diff afterward. `just check` writes nothing and consists of three grouped aggregates—`docs-check`, `back-check`, and `web-check`—plus the shared `just security`.

The verbs are identical within each group, so there is no command list to memorize: `<group>-static` reads source, `<group>-test` runs tests, `<group>-build` builds an artifact, and `<group>-regress` runs the built artifact in the real engine. The complete table is in `docs/engineering/quality-gates.md`.

`pre-commit` maintains the fast path (`docs-static` + `docs-test` + `back-static` + `just-fmt`); the remaining documentation, backend regression, package/install, web, E2E, profile, and security suites run in CI on pull requests and on pushes to `dev` and `main`. There are no separate `ci` / `pre-push` recipes because they would only be aliases for the CI gate.

### PostgreSQL for platform tests

Platform integration and ASGI tests (`tests/api/platform`, `tests/integration/platform`) require a live PostgreSQL 16 instance. Without `AI_STP_TEST_DB_URL`, they are **skipped**.

Locally (a separate container with a port exposed on the host; dev-compose exposes Postgres only to the internal network):

```bash
docker run -d --name ai_stp-test-postgres \
  -e POSTGRES_USER=ai_stp -e POSTGRES_PASSWORD=ai_stp_dev -e POSTGRES_DB=ai_stp \
  -p 127.0.0.1:55432:5432 postgres:16

export AI_STP_TEST_DB_URL=postgresql+asyncpg://ai_stp:ai_stp_dev@127.0.0.1:55432/ai_stp
just back-test
# or the full gate:
just check
```

In CI, the `check` workflow sets the same variable against its `postgres:16` service (the CI-side value is `postgresql+asyncpg://ai_stp:ai_stp_dev@127.0.0.1:5432/ai_stp`). Do not use production data or commit real passwords; the throwaway credentials above are sufficient for tests.

## Starting a change

1. Read `AGENTS.md`.
2. Create a work branch from current `dev` under `docs/engineering/git-workflow.md`; the name must use one of the accepted prefixes — `feat/`, `chore/`, `docs/`, `test/`, `fix/`, or `refactor/` — or branch policy rejects it. Publish the branch and open a PR into GitHub `dev`; after green CI on the exact final HEAD, merge it into `dev`. Release is a separate promotion PR from same-repository `dev` into `main`; local `dev` is never pushed to `main` directly.
3. Find the applicable active specification.
4. If requirements are absent or contradictory, fix the specification before the code.
5. In the draft PR, state the acceptance criteria, plan, affected contracts, and validation commands.
6. Only then begin implementation.

## What not to do

- do not run remote scripts without reading them first;
- do not use `sudo` for project tools;
- do not add APM, SX, or the closed system-authoring environment as a mandatory dependency;
- do not modify external repositories without an explicit task;
- do not treat green documentation CI as proof that the future product works;
- do not change behavior without simultaneously updating the affected specifications, documentation, tests, and runbooks.
