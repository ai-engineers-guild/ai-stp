---
description: "Decision not to place protections on repository contributors: the gate proves the tree rather than authorizing a person."
last_verified: "2026-08-22"
---

# ADR-0115: The repository does not guard the people working in it

Status: accepted.

## Context

`quality-gates.md` described the target state: branch protection on `main`, one
required approval, dismissal of stale reviews, required approval of the latest
push, resolution of all conversations, `enforce_admins`, prohibition of force
pushes and deletion, and a separate `pypi` environment with a reviewer and tag
policy. The desired state was stored mechanically in
`.github/release-protection-policy.json`, and `just release-protections`
compared it with the live API. `#188` was the task to "enable this when the
repository becomes public."

The repository became public. It turned out that nothing should be enabled,
for the following reason.

The primary contributor to this repository is not a human with a mouse but a
coding agent. It works in a "change → gate → publish" cycle, and every listed
item inserts a step the agent cannot perform: approval requires a second human,
`require_last_push_approval` invalidates approval after any review-driven edit,
and `dismiss_stale_reviews` does so after any base update. There are two owners,
and one is the same person who would approve.

None of these rules checks the change itself. The gate checks the change: three
operating systems, types, lint, tests with a coverage threshold, contract
checks, and the publication report. The gate proves the tree. Approval proves
that someone pressed a button.

## Decision

The repository imposes no protections on contributors: no branch protection,
required approvals, protected environments, or tag rules.

`release-protection-policy.json`, `verify_protections.py`, the
`just release-protections` recipe, and the protection activation runbook are
removed: they describe a state that will not exist.

What remains, and why it is not "protection":

- **the gate** concerns the tree, not the person, and publication does not
  proceed without it;
- **explicit confirmation of an irreversible product operation** is a product
  property, not a repository mode: `plan` → `digest` → `confirm` exists so the
  agent confirms exactly what was shown, and refusal does not depend on it;
- **the allowlist of publishable paths** (`ADR-0108`) answers "what can be
  published," not "who may press the button."

The distinction follows one line: a rule that checks the **change** remains; a
rule that checks **permission** goes away.

## Consequences

`main` is written directly. History is linear not because force push is
prohibited, but because an error in `main` is fixed forward—this is already a
rule in `git-workflow.md`, and it has not changed.

A release no longer requires an environment reviewer or a tag matching a
pattern. Version and tag remain the owner's decision; the difference is that
the platform does not guard them.

The cost is explicit: nothing stops an accidental push to `main`. We accept it
because the converse cost is a blocked agent stopping all work, while a
reversible error in linear history costs one commit.

`#188` is closed as decided in the opposite direction, not as implemented.

## Alternatives

**Enable protections and allow the agent to bypass them.** The rule would then
exist only for a human while formally applying to everyone. A rule that does
not apply to the most frequent writer is not protection but a description.

**Leave the policy as a declaration without enabling it.** That was the prior
state: the document described a nonexistent state,
`just release-protections` compared reality with the nonexistent state, and
`#188` remained open. A document that diverges from reality is precisely the
error that `AGENTS.md` prohibits explicitly.
