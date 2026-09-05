---
description: "Full-task authority executes without extra prompts; unverified stays labeled; active-target change is staged."
last_verified: "2026-09-04"
---

# ADR-0150: Full-task authority does not re-prompt

Status: accepted.

Supersedes the parts of `ADR-0118` that required a fresh human grant to
install an unverified object, or that treated any in-place change of the
running agent's active target as forbidden.

## Context

`ADR-0118` removed routine engineering questions and kept five stops that
expand access or cannot be undone. Two of those stops now conflict with the
owner's agent-first direction:

- **Unverified install.** Under full-task authority the agent may use an
  object that is not platform-verified. Asking again does not make it
  verified. It only pauses work.
- **Never change the active target.** `SPEC-008` `REQ-810` banned in-place
  overwrite of the session's own target. That correctly forbids a half-updated
  environment. It incorrectly forbade a staged replacement and restart.

Plans, digests, preconditions and recovery remain mechanical. They are not
human-approval stages.

## Options

**Keep `ADR-0118` as written.** Unverified objects and active-target upgrades
stay blocked on a person. Autonomous standard presets cannot complete.

**Drop every remaining stop.** Irreversible deletion and linking someone
else's account would proceed without a path back.

**Keep irreversible and third-party access stops; execute the rest under
task authority.** Unverified stays labeled. Active-target change is staged,
verified, then switched.

## Decision

Under an authorized full-task / full-auto profile:

- The agent researches, chooses, implements, tests, commits, publishes and
  deploys without a fresh human grant per object, capability or plan.
- An unverified object may be installed when the task authorizes it. It
  remains `unverified`. Authority is not verification.
- Changing the running agent's active setup stages the new environment,
  records a handoff, switches, and confirms after restart. Partial in-place
  mutation of the live target remains forbidden.
- Uncertainty triggers more code, tests or a reversible experiment, not a
  question whose only purpose is permission.

A separate owner decision remains required for:

- deletion of data, a target, or backups with no recovery path;
- linking **someone else's** account or new third-party credentials;
- elevation of system privileges;
- changing an existing object's publicity or access rights.

## Consequences

`AGENTS.md`, `skills/canonical/ai-stp/references/decisions.md` and
`SPEC-008` `REQ-810` follow this record. Generated skill projections are
regenerated from the canonical skill.

CLI `confirmation: plan_digest` stays a machine binding. It is not a prompt
for a person.

## Revisit conditions

Revisit if a staged handoff cannot be implemented for a supported harness,
or if an unverified install is observed being reported as verified.
EOF
