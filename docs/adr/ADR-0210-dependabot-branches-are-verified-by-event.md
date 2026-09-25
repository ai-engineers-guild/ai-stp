---
description: "Allow same-repository Dependabot pull requests through the branch-name contract after verifying GitHub event identity."
last_verified: "2026-09-25"
---

# ADR-0210: Dependabot branches are verified by event

Status: accepted. Narrows the conventional branch rule retained by ADR-0180.

## Context

Dependabot opens update pull requests under `dependabot/` branches. The `CT014`
documentation contract rejects those names, so otherwise valid dependency
updates fail the repository gate. Five updates in September 2026 had this
failure. The rule still needs to reject arbitrary nonconventional contributor
branches.

## Options

- Keep the rule and manually copy every bot update to a conventional branch.
  This preserves the existing check but repeats work on each update.
- Exempt every `dependabot/` branch by name. This is simple but allows a human
  branch with that prefix to bypass the conventional naming contract.
- Exempt only a same-repository pull request whose GitHub event identifies
  `dependabot[bot]` as author and whose head ref matches the checked branch.

## Decision

Use the event-verified exception. `CT014` reads the GitHub pull-request event
and requires the bot author, exact head ref, and same-repository head. Missing,
malformed, or mismatched event data fails closed. Human and fork branches keep
the conventional prefix rule. The `main` promotion boundary is unchanged.

## Consequences

Dependabot updates can pass documentation CI without being copied to a human
branch. Contract tests cover the accepted event and rejected author, source,
ref, event type, and malformed payloads. The event parser is only a CI naming
check; it does not replace dependency review or the full merge gate.

Rollback reverts this decision and its linter change through a work PR, after
which bot updates again require conventional branches. No branch history or
dependency data is deleted.

## Revisit conditions

Revisit when Dependabot changes its event identity or the repository adopts a
different dependency-update bot.
