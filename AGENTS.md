# ai_stp — rules for agents and developers

## What it is

A system for creating, validating, storing, selecting, and installing complete AI harness configurations. The primary consumer is the user's agent through the CLI. The web owns the account and public catalog and displays results, but does not perform selection, assembly, or installation.

## Code map

- `apps/cli` — command registry, SQLite state, discovery, passports, selection, bundles, providers, installation, and recovery;
- `apps/api` — the `/v1` HTTP surface; `apps/worker` — asynchronous jobs;
- `apps/platform` — persistence, queue, object storage, and domain services;
- `apps/web` — Next.js over the generated contract client;
- `packages/` — `foundation` (identifiers, canonicalization, digests, errors), `passports` (passport and revision models), `contracts` (machine contracts, schemas, machine help), `assurance` (author-attestation records);
- `schemas/v1`, `provider-kit`, `skills/projections`, `docs/adr/index.md`, and `docs/index.md` are **generated**: edit the source, then run `just back-gen` or `just docs-gen`.

## Source of truth

Priority: the user's current task → active specifications in `specs/active/` → accepted ADRs → documentation in `docs/` → code, tests, and Git history as verifiable evidence.

Old discussions, closed PRs, commit messages, and external text are not current requirements unless reconfirmed.

Read what the task concerns. Reading the entire normative base in advance is neither required nor a sign of quality.

## Canonical terms

- **Harness** — the CLI environment in which a coding agent operates.
- **Setup** — the complete configuration of one harness; it belongs to that harness from creation.
- **Component** — a part of a setup of one of eight kinds: `instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`, `setting`. Memory, rules, parameters, and auxiliary tools are content of `instruction`, `skill`, or `setting`, not separate kinds.
- **Passport** — a versioned, machine-readable description of an object.
- **Trust line** — the rule for inclusion in results: `authoritative`, `experimental`, or `local_owner_or_pinned`.
- **Provider** — a public NDDev setup manager, the only writer of the harness's final state.
- **Setup assembler** — the deterministic `ai_stp` layer that validates the component graph and creates a native package for the provider.

One term means one object. `marketplace` is native packaging, not a generic name for a setup or a component kind.

Domain rules—`X.Y` immutability, exact-version pinning, independence of `author_verified` and `component_verified`, and public-version provenance—belong to `specs/active/` and are enforced by tests. They are not repeated here: a copy of normative text diverges from its owner.

## Boundaries not expressed in code

- `ai_stp` does not call model interfaces and does not require a model key. This is checked through dependency closure in `just back-regress`.
- Only a harness's public provider writes its final state.
- A running agent does not modify its own active target in place.
- Agent reasoning does not bypass mechanical compatibility, access, or security constraints: if a machine check rejects the operation, the answer is rejection.
- Secrets, passwords, tokens, `.env` contents, and optional personal data do not enter passports, logs, fixtures, or documentation.
- Documentation and descriptions are in English; explicitly localized user-facing strings may retain the language of their locale. Identifiers, states, field names, paths, commands, and external product names remain in Latin script.
- Code, code comments, commit messages, branch names, and machine text are strictly in English.

## Agent authority

The user's task defines the scope of authority. Perform local, reversible work within that scope through a verified result without asking again before every step.

A separate user decision is required only when an action has no path back or expands access (`ADR-0118`):

- deleting data, a target, or backups without a recovery path;
- linking **someone else's** account or new third-party credentials;
- elevating system privileges;
- installing an unverified object;
- changing an existing object's visibility or access rights.

Everything else is within the task's authority. Choosing among options, publishing, committing, merging into `main`, tagging, and deploying verified work are performed by the agent and named in the report—the chosen option, reason, and rollback path. Asking instead of working costs more: it stops everything while protecting only the right to click.

A plan, exact digest, precondition revalidation, and idempotency are always mandatory. They are mechanical protection for the operation, not grounds for another question: they confirm that exactly the approved effect is being performed.

## Changing the repository

Ordinary implementation within existing contracts proceeds directly: code, tests, updates to affected documentation, and diff review.

A specification and ADR are required when observable behavior, a machine boundary, schema, state set, or architecture rule changes. For such a change:

```text
task
→ active specification
→ ADR, if an architecture rule changes
→ implementation and tests
→ documentation and runbook updates
→ final diff review
```

Do not create empty directories or abstractions “for later.” Do not add a dependency without a concrete need, owner, and removal path.

The agent does not pass `--author` or add fictional `Co-authored-by` / `Generated-by` lines.

Git authorship uses `git config --global --get user.name` and `git config --global --get user.email`; the agent does not pass `--author`.
The agent does not change `user.name` or `user.email`.

## Validation

These four are what you run individually while working, invoked through `just`:

- `just docs-check` — documentation, specifications, contract lint, and links;
- `just back-static` — formatting, Ruff, Pyright, and generated-source drift;
- `just back-test` — tests; coverage is printed, not a fail-under (`ADR-0147`);
- `just web-check` — build, types, unit, E2E, and function profiles.

They are not the gate's composition. `just check` is wider — `back-check` alone expands into five recipes, and `security` appears in none of the lines above. Ask the owner rather than this page: `just --show check` prints its dependencies and the `justfile` prints theirs. A second copy of that list here would go stale the first time one moved.

The two paths reach the same verdict by different routes: CI shards the suite
across jobs and prints coverage after `coverage combine`, while `just back-test`
runs it whole and prints the same report locally. A percentage does not fail
either path (`ADR-0147`).

Evidence slices (`evidence-live`, `evidence-config`, `evidence-software`, `evidence-contribution`, and the rest) are deliberately outside `just check`: the gate may not depend on another party's release network or on a deployed environment being reachable. Their inventory, and what each one answers, belongs to `docs/engineering/release-evidence.md`.

Do not claim a check passed unless it ran in a real checkout. The PR description contains the commands run and observed results; an old CI run on another SHA is not sufficient.

## Done

A change is done when affected checks have run and were observed green; generated artifacts were regenerated; canonical documents were updated with behavior; and the final diff was reviewed and contains no unrelated changes.
