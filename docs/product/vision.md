---
description: "The problem, users, value, and positioning of ai_stp."
last_verified: "2026-08-29"
---

# Product vision

## Problem

Developers spend time manually finding and configuring instructions, skills, MCP, hooks, agents, commands, and plugins for every harness and project. Components use different formats, conflict, become outdated quickly, and rarely include verifiable compatibility and risk information.

## Solution

`ai_stp` creates a unified machine-readable cycle:

```text
developer + project + harness
→ passports
→ component search
→ mechanical constraints
→ agent decision
→ coherent setup assembly
→ verification
→ safe installation
→ history and synchronization
```

## First user

A developer who wants to quickly obtain a working full-auto harness for the current project. Their coding agent interacts directly with the CLI: the product treats the agent as its primary consumer.

There is one user, who is also the owner: the MVP describes one developer working with their own projects and devices. This concerns whom the product is for, not who builds it: `ai_stp` itself is developed by multiple contributors, whose working rules live in `docs/engineering/git-workflow.md`. Two people collaborating on one project is not supported — a setup belongs to an account, not a repository, and a colleague who clones the repository assembles their own setup. This is a constraint, not an oversight: a team, a shared setup, and its review would require their own ownership model and a way to resolve conflicts between people.

This is not the same as sharing an object. An account can grant another account access to its private component or setup — that is an author-recipient relationship in the catalog. What does not exist is a shared working project setup that two people modify concurrently.

The product lives with the project rather than ending after the first installation: the daily cycle in `user-flows.md` is as much a part of the product as the first run.

Roles are separated explicitly. The CLI deterministically discovers facts, verifies and stores passports. The user's agent interprets findings, asks questions, and assembles the composition. The user confirms unknown and risky matters. Under `ADR-0022`, the CLI, passports, validation, and required publication do not call model interfaces or require a model key; `ADR-0131` permits only optional server-side enhancement of an already complete public presentation projection.

## Authors

Any user can publish from day one: publications are not pre-moderated, and problematic objects are handled through closed report cases under `ADR-0031`. The guild nevertheless distinguishes two kinds of authors: verified authors whose identity or namespace ownership the platform has verified, and ordinary users.

Verification has two independent axes: the author is verified, and a specific object version is verified. Neither follows from the other, and both axes are visible and filtered separately. They determine which trust lane receives the object: the authoritative lane, the experimental lane with explicit user consent, or the lane for owned and exactly pinned objects. The lane rules belong to `ADR-0016`.

Under `ADR-0034`, the launch catalog is first-party: the guild publishes base setups for supported harnesses from a verified namespace; the launch barrier is a base setup for each of the seven (`ADR-0120`), and the corpus satisfies it. User publications supplement the catalog, but cold start does not depend on them.

`author_verified` is granted through two paths: on author application after verifying ownership of a GitHub profile or organization, and by personal invitation from the platform owners. Both paths are manual and auditable under `SPEC-007`; the verification procedure is the runbook `docs/operations/runbooks/author-verification.md`.

Verified confirms provenance, not the safety of the content.

## Core value

The product does more than store links to components. It:

- understands the developer's environment and preferences;
- indexes the project;
- finds ready-made setups and individual components by tags, filters, and trust line;
- connects them into the native configuration of a specific harness;
- shows provenance, verification, trust line, and constraints;
- applies the configuration through a verified provider with backup and recovery;
- preserves an existing configuration as a personal setup instead of overwriting it.

The final choice remains with the agent and user: the product returns eligible candidates and explains them, but does not present its ordering as the only correct one.

## Three modes

- **Local:** fully without an account or server.
- **Public:** anonymous search and reading of the public catalog.
- **Authenticated:** private objects, synchronization, publication, devices, and grants.

After successful initial setup, local mode works without a network. The exact boundary between offline and network operations belongs to `ADR-0019`.

## Positioning

`ai_stp` is not a universal package manager, only a skill catalog, or only a security scanner. It is a layer for selecting, assembling, and safely managing the lifecycle of complete AI harness configurations.

## Ownership

The catalog belongs to the guild. NDDev provides public harness providers — the installation systems the company itself uses. The platform is licensed under AGPL-3.0-or-later; user-published objects remain under their authors' licenses.

## Measure of MVP success

The MVP succeeds when the guild owners manage their real projects entirely through `ai_stp`: passports, selection, assembly, installation, and the daily cycle — without returning to manual harness configuration. This is the criterion of daily internal use; external installations and counters are desirable but secondary and do not determine release.

## Money

The MVP is free: payments, payouts, and paid access are not included, and no economic model is currently being designed. The door is deliberately left open: paid access may be possible in the future, and `ADR-0004` establishes a natural boundary for it in advance — the major version line. This is groundwork, not a promise: neither timing nor form is fixed, and the product remains entirely free until a separate decision by the owners.
