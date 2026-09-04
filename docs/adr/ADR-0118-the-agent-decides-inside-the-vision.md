---
description: "Decision to treat option selection, publication, and code promotion as part of the agent's authority, reserving a separate decision only for irreversible and external actions."
last_verified: "2026-09-01"
---

# ADR-0118: The agent decides within the vision

Status: accepted. Partially superseded by `ADR-0150` for unverified install
and active-target change.

## Context

`ADR-0115` removed protections from people working in the repository: the gate
checks the change, while approval would check permission. The same line was not
carried through the "Agent authority" section of `AGENTS.md`, which remained a
list of eight reasons to stop and ask.

Two of the eight reasons proved costly:

- **"an unselected option that changes the outcome"** covers almost every
  engineering choice;
- **"Git push, PR, merge, or deployment not requested by the task"** covers
  every promotion of the work, even when the work is complete.

Observed consequence: the last two sessions ended with four questions instead
of a result. Every question complied with the section literally, and none
protected anything irreversible. While awaiting answers, production could not
build for twelve hours, and all public documentation pointed to a repository
returning 404. Neither was noticed because there was no time to look.

Meanwhile, the owner repeatedly and explicitly said the opposite: "make
decisions yourself," "I trust you," "merge into main," "deploy everything,"
"publish everything there is," and finally "without guards, blockers,
prohibitions, or conditions—remove all of that instead."

Permission inferred from correspondence will be inferred again by the next
session, or not at all. It must be recorded where the rules are read.

## Options

**Keep the list and rely on the owner's words in every session.** Costs nothing
today and repeats the cost tomorrow: the document continues to advise stopping,
and an agent reading it faithfully stops.

**Remove the section entirely.** Inexpensive and wrong. Some items protect the
operation itself, not permission: deletion without a recovery path cannot be
undone by consent after the fact.

**Carry the line from `ADR-0115` through the section.** Keep what describes a
property of the operation; remove what describes the right to perform it.

## Decision

Only actions with no recovery path or that expand access require a separate
owner decision:

- deletion of data, a target, or backups without a recovery path;
- linking credentials or an account;
- elevation of system privileges;
- installation of an unverified object;
- changing an object's visibility or its access rights.

Everything else is within the task's authority. In particular, the agent
**independently**:

- chooses among options and states the choice in the report;
- publishes, commits, merges into `main`, tags, and deploys once the work is
  verified by the gate;
- closes and reframes tasks resolved in another way.

The boundary remains exactly where it was in `ADR-0115`: a rule checking the
**change** remains; a rule checking **permission** goes away.

A plan, exact digest, repeated precondition checks, and idempotency remain
mandatory. They are mechanical protection of the operation, not a reason to ask.

## Consequences

A report becomes mandatory where a question previously existed: the chosen
option, reason, and rollback path are stated after the action rather than agreed
before it. This costs the owner less: reading one sentence instead of answering
a question asked without context.

The cost is explicit: the agent will make a decision the owner would make
differently. We accept it because the opposite cost is measured—two production
defects persisted for exactly as long as one answer would have taken.

Publication is removed from the prohibition list, but not from the obligation
list: it still passes through `plan` → `digest` → `confirm`, while the
`ADR-0108` allowlist still determines what may be published at all. Changing
the visibility of an **existing** object remains with the owner—it is an access
right, not promotion of work.

`AGENTS.md` is updated with this decision; the eight-item list is replaced by a
five-item list.

## Amendment of 2026-08-27: whose account, not which action

The "linking credentials or an account" item continued to cause stops where
permission had already been given. It describes an action class, but the cost
depends not on the class but on **whose** account it is.

Measured consequence: `evidence-live` names three unproven items: Google login
with device registration, GitHub login on an isolated account, and device
revocation followed by login. The same three block first-party setup publication
to the live catalog, `evidence-sync`, and the writing half of
`evidence-publication`. One login unlocks four things, yet the item stopped it
despite repeated explicit owner permission, including "I allow any account"
and "I logged into Google Chrome on my PC—use everything."

This is exactly the argument behind this record: permission inferred from
correspondence will be inferred again by the next session, or not at all.

**Amend the item rather than remove it.** Logging into the **owner's** account
with their browser on their machine has a recovery path (logout and device
revocation are ordinary product commands) and gives nobody access the owner did
not already have. It is within the task's authority.

A separate decision remains required where access truly expands: linking
**another** account, issuing or entering **new third-party** credentials, or
linking an account to an object the owner does not own.

What **does not** and must not change: the session is issued by real browser
login, not a script. A script able to issue a session would prove the wrong
path—`evidence-sync` and `evidence-publication` require a completed login for
that reason. The amendment removes the question, not the step.

The list becomes:

- deletion of data, a target, or backups without a recovery path;
- linking **someone else's** account or new third-party credentials;
- elevation of system privileges;
- installation of an unverified object;
- changing an object's visibility or its access rights.

## Amendment of 2026-08-30: the digest is the confirmation

This record's line was carried through `AGENTS.md` but not through the **CLI's
own surface**, where the same stop is expressed mechanically.

Enumerated rather than recalled: of 136 declared commands, 24 require
confirmation—21 through `explicit_flag`, 3 through `plan_digest`. Twenty of the
twenty-one are justified by the list above: `device reset`, component and setup
publication, grants, reports, telemetry, `install apply`, provider replacement
and adoption, attestation signing, `sync`, and tool and harness deletion.

Four are not:

| command | action | already requires |
|---|---|---|
| `component scaffold apply` | creates a new directory | `--expected-plan-digest` |
| `component passport update` | creates a child revision; the parent remains | `--expected-revision` |
| `eval run` | local static checks, idempotently | `--expected-plan-digest` |
| `setup import register` | writes the local registry | `--plan-digest` |

None deletes without recovery, links another person's account, elevates
privileges, installs an unverified object, or changes anyone's visibility. Each
**already** must name an exact expected value checked lower in the stack:
`apply_scaffold` compares the digest with the recalculated plan,
`component_passports.update` checks `revision_id`, `evaluation.run` checks the
plan digest, and `register_graph` checks the proposal digest.

Then `--confirm` adds nothing atop an exact digest. A digest is stronger
confirmation: it says **which exact** plan is confirmed, while a Boolean flag
says only "yes." Yet the refusal code is `AI_STP_USER_DECISION_REQUIRED`,
literally "ask the user": exit class 4, another agent round, and exactly the
kind of stop this record removed.

Decision: where an operation is local, reversible, and already requires an
exact expected value, that value is the confirmation. Separate `--confirm` is
removed from these four, and their `confirmation` becomes `plan_digest`. Both
remain where an operation is external or irreversible.

A minor imprecision is stated explicitly: the `plan_digest` kind for
`component passport update` covers `--expected-revision`, not a plan digest.
The kind means "confirmed by the named exact value," and its name comes from
its first use. Renaming it would change a published contract for cosmetic
reasons, so it was not done.

## Amendment of 2026-09-02: five stops with nothing behind them

Counted again against the current registry, the previous amendment's rule —
where an operation is local, reversible and already names an exact expected
value, that value is the confirmation — had not been applied to two commands
that met it, and three other refusals asked the caller to repeat a command's
only meaning before being answered:

| command | asked for | already carried |
|---|---|---|
| `provider update apply`, `provider reinstall apply` | `--confirm` | `--expected-plan-digest` |
| `component version release --major` | `--confirm` beside `--major` | the `--major` decision itself |
| `select confirm` | `--confirm` beside the proposal | the exact proposal, private and local |
| `component passport validate` | `--for-publication`, required | the command's one profile |
| `help` | `--agent`, required | the command's one answer |

Decision: the two provider `apply` commands become `plan_digest`; `select
confirm` and `component version release` lose `--confirm`; `--for-publication`
and `--agent` stay accepted and stop being demanded. What remains behind a flag
is exactly the list this record keeps: deletion without recovery, another
party's account or new credentials, privilege, an unverified object, and the
publicity or access of an existing object — plus the end user's own consent.

## Reconsideration conditions

Reconsider if the agent makes a decision whose reversal costs the owner more
than asking would have; then that specific class of decisions returns to the
list, not the entire list.
