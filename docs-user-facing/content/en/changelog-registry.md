---
type: changelog
slug: web-feature-registry
locale: en
title: CLI and catalog changelog for this line
description: "What this line of ai-stp-cli actually ships: assembly, checks, sync, and the limits of the MVP."
published_at: 2026-08-10
tags: [changelog, cli]
draft: false
---

This changelog describes the current `ai-stp-cli` line, package version `0.0.15`. It is a product log for operators and agents, not a note about web deploy profiles.

The executable is `ai-stp`. The PyPI distribution is `ai-stp-cli`. Every command an agent should copy from documentation is meant to be run with `--json`.

## Added

The CLI is the working surface. It discovers native components, records passports, searches the public catalog without an account, compiles an exact setup graph, and asks the harness provider for a plan. Apply, backup, status and named rollback go through that provider. The CLI does not write native harness files itself.

Local-first identity is present: `device init`, developer and device passports, a SQLite registry, and content-addressed local storage. Cloud sign-in with Google or GitHub unlocks private revisions, `sync push` / `sync pull`, publication, devices and grants. Local work does not require an account.

Publication is plan-then-confirm. A public `X.Y` is immutable bytes plus a version passport, sourced from a public GitHub repository at an exact commit and subpath. Device signatures bind the confirmation record. Author verification and component verification are stored and shown as independent axes.

Safety checks run as a staged, non-executing suite before a public component is treated as verified. Required checks block publication when they fail or cannot run. Optional scanners produce warnings or incomplete coverage; an unavailable engine is never a pass.

Private sync is an ordered account ledger. `sync pull` applies one bounded page from the last confirmed cursor. Catalog listing is a separate public pagination model and may end at `null`.

The website shows the public catalog, publisher profiles, account, devices, publications and this content hub. Human and machine projections of the same public pages exist as equal routes. The website does not assemble or install a setup.

## Changed and pinned

Exact pins replaced ranges. A setup belongs to one harness from creation. Changing composition creates the next minor version. A new major line is an explicit `--major` decision, never a default.

Trust lines are `authoritative`, `experimental` and `local_owner_or_pinned`. Experimental objects appear only with explicit consent, in a separate section, and are never auto-selected. Local owned or pinned objects are not thereby platform-verified.

Provider writes are digest-bound. Stale plans are refused. Interrupted apply is recovered by reading status, not by guessing a second apply.

## Command families on this line

The registry ships 142 commands. The help-center map groups them; machine help is still `ai-stp help --agent --json`. Families that exist today:

- observe: `version`, `doctor`, `help`, `capabilities`;
- identity: `device`, `passport`, `auth`, `config`, `consent`, `telemetry`;
- authoring: `component discover` / `adopt` / passport / source / `version release` / `skill validate` / `publication`;
- catalog: `registry search` / `show` / `version` / `fetch` / `acquire` and the SX/APM port;
- assembly: `select`, `setup compose` / `import` / `update` / `publish`;
- apply: `install plan` / `approve` / `apply` / recover, `provider`, `target`;
- account: `sync`, `grant`, `owner`, `report`.

There is no `component inspect`, no `setup show`, and no `ai-stp contact`. Flags are not copied into articles: they move with the installed CLI.

## Limits that remain

Pi, OpenCode, Cursor and Antigravity are beta. Claude Code, Codex and Grok Build are the primary path. `undefined` is a limited row of portable conventions, not a harness you auto-install into.

There is no team shared working setup. There is no model API inside ai_stp. There are no ratings or public discussions. There is no absolute promise that a published object is harmless.

A like is not a pin. A grant for major `1` does not open `2`. Revoke is forward-only: local bytes on a grantee's disk may remain. An unavailable safety engine never counts as a pass.

## How to read this log

This is not a git history. **Added** is the working surface on `0.0.15`. **Changed and pinned** is the contract that will not quietly relax. **Limits that remain** are refusals, not a backlog you should wait out.

After you install or upgrade `ai-stp-cli`, confirm that this log describes the binary on `PATH`:

```bash
ai-stp version --json
ai-stp doctor --json
ai-stp help --agent --json
```

`cli_version` must be `0.0.15` for this log to apply. If machine help names a flag this article does not, follow the binary. If an article names a command this registry does not ship — there is no `component inspect`, no `setup show`, no `ai-stp contact` — the article is wrong.

The website changelog type in the content hub is this document. A MkDocs theme bump or a web deploy profile is not a new CLI line. Staff URLs are not a user surface and do not belong in this log.

See also: [CLI](https://ai-stp.aiguild.space/en/docs/cli) in the help center.
