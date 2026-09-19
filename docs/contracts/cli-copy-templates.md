---
description: "Canonical CLI templates for web UI copy blocks (SPEC-037)."
last_verified: "2026-09-18"
---

# CLI copy templates

The requirements owner is `SPEC-037` (`REQ-3706`, `REQ-3707`). The web UI and
prototypes do not invent verbs: commands come from this contract. HTML mockups
containing `ai-stp use` are not normative.

The sole executable source of templates is `ai_stp_contracts.cli_copy`. The
tables below describe it rather than duplicate it: drift is caught not by
comparing two lists, but by passing the rendered string through the real command
parser (`tests/contract/test_cli_copy_templates.py`). Comparing lists has already
failed once: both lists matched each other but not the command registry, and
every copy button produced a command rejected by the CLI.

## Identifiers in templates

- `{kind}` — object kind: `component` or `setup`. Required: `registry show` and
  `registry version` declare `--kind` as a closed set.
- `{stable_id}` — stable object ID (`component_…` / `setup_…`).
- `{version}` — exact `X.Y` version. It is a separate argument, not an `@`
  suffix: the CLI does not parse such syntax.
- Paths and tokens are **not** substituted into UI commands.

## Public object / version

| Context | Template |
|---|---|
| Show a published object | `ai-stp registry show --kind {kind} --id {stable_id}` |
| Show an exact version | `ai-stp registry version --kind {kind} --id {stable_id} --version {version}` |
| Everyday catalog "Use via CLI" | `ai-stp task start --intent install --idempotency-key install-session-01 --json` |

## Owner next steps (empty / sync)

An empty state receives a complete everyday argv. Neither template needs a
path or secret, so the copied string is safe; a step requiring a root,
harness, or confirmation cannot be rendered without substituting something
this contract prohibits placing in a UI command.

| Context | Template |
|---|---|
| The owner has no components yet | `ai-stp task start --intent author --idempotency-key author-session-01 --json` |
| The owner has no setups yet | `ai-stp task start --intent install --idempotency-key install-session-01 --json` |
| Device login | `ai-stp task start --intent account --idempotency-key account-session-01 --json` |
| CLI installation (landing) | `uv tool install ai-stp-cli` |
| Compact intent discovery | `ai-stp task intents --json` |
| First-run harness discoverability | `ai-stp task start --intent initialize --idempotency-key initialize-session-01 --json` |

`ai-stp` is the executable name; `ai-stp-cli` is the distribution name.
Installing by executable name fetches a package that this project does not
publish.

## Interface rules

1. The copy button inserts **exactly** the template string after substituting
   `{kind}` / `{stable_id}` / `{version}`.
2. The interface does not promise installation through the browser and does not
   render a web-based passport editor.
3. A copy failure is shown explicitly; success produces brief feedback without
   falsely claiming "installed."
4. The documentation link points to `/docs` (the CLI section), not an arbitrary URL.
