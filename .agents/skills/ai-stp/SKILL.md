---
name: ai-stp
description: >
  Operate the ai-stp CLI to prepare project environments across harnesses,
  preserve and restore existing setups, inspect, select, compose, install, recover,
  author, and publish AI harness setups and components. Use when the user asks
  to prepare a harness, install or repair a setup, manage passports, search the
  catalog, sign in to ai-stp, publish a component, or drive any `ai-stp`
  command — even if they say “NDDev”, “ai_stp”, or “the setup CLI” instead of
  the skill name. Do NOT use for calling a model API, editing a harness target
  by hand, writing a generic SKILL.md for some other product, or answering
  questions that do not involve this CLI.
license: AGPL-3.0-or-later
metadata:
  source: canonical
---

# ai-stp

Help the user's coding agent choose, install and maintain complete harness
setups through the installed CLI. Finish the requested operation and report
what was actually verified. The CLI owns acquisition, composition, backup,
plan, approve, apply, verify, retries, and recovery.

## Start here

You are the coding agent. Run `ai-stp` yourself with your tools. Do not ask
the human to paste or execute those commands. A printed command is not a completed operation.

1. Run `ai-stp task intents --json` and pick one shipped intent. If the
   executable is missing, follow [bootstrap](references/bootstrap.md).
2. Call `ai-stp task start` for that intent.
   `envelope.continuations[0].actor` is a JSON field, not the user's identity.
   When that field is `cli`, execute `argv` with your tools. When it is
   `human`, do not execute that `argv`; relay `questions[0]` through
   `ai-stp task answer` using bound `task`, `revision`, and `question-id`.
   When it is `external`, show the payload once and later call
   `ai-stp task continue`. Do not invent `task status` or `task info`.
3. Stop when there are no continuations. Report payload verification, not
   envelope `ok` alone.

Only `task intents --json` fixes CLI flags in this package. Other command
paths describe a workflow; their executable arguments come from continuation
`argv` or from machine help. Use machine JSON for subsequent calls.

Do not run `ai-stp doctor` or dump `ai-stp help` as a prelude to every
request. Completing inspect is enough when the user asked what is wrong.

## What is being installed

| Object | Meaning |
|---|---|
| ai-stp CLI | This product; its own updater replaces its installed package |
| Control Skill | These instructions, installed separately into the agent's harness |
| Provider | Setup manager automatically acquired by the CLI when needed |
| Harness program | The coding-agent executable; its installation prefix is separate from its configuration target |
| Setup | One harness's exact versioned configuration and component graph |

Installing a program does not install a setup. Downloading a setup does not
apply it. Preparing or approving a plan does not prove an installed result.

## Router

Read one relevant playbook first. Consult [envelope](references/envelope.md)
for response handling, [decisions](references/decisions.md) for task authority,
and [traps](references/traps.md) when a returned state is ambiguous.

| User intent | Open |
|---|---|
| first run, missing CLI, identify the current project | [bootstrap](references/bootstrap.md) |
| local settings and passports | [onboard](references/onboard.md) |
| install a ready setup, update, preserve or restore configuration | [install](references/install.md) |
| find an exact public or granted object | [catalog](references/catalog.md) |
| build a setup from components, adapt it to a harness | [compose](references/compose.md) |
| prepare a project or several harnesses | [environment](references/environment.md) |
| discover local harnesses, projects or components | [inspect](references/inspect.md) |
| compare selected and installed state, drift | [daily](references/daily.md) |
| recover an interrupted or partial operation | [recover](references/recover.md) |
| update ai-stp itself | [self-update](references/self-update.md) |
| create, adopt, validate or publish content | [author](references/author.md) |
| install a harness program or maintain a provider | [provider](references/provider.md) |
| sign in, manage access or synchronize | [account](references/account.md) |
| install or refresh this control Skill | [self](references/self.md) |

## Hard rules

- Machine help owns supported commands, parameters, schemas and error handling.
  Execute returned next actions only after resolving their actual inputs.
  Prefer continuation `argv` over typing expert leaves.
- Do not choreograph `install plan`, `install approve`, or `install apply`.
  The install intent drains those in-process.
- Do not type `setup compose plan`, `setup compose apply`, `setup update apply`,
  `component adopt`, or `component scaffold`. Use `change` to alter a saved
  setup and `author` to register a directory.
- Do not type `setup restore plan` or `setup preserve plan`. Use `switch` to
  return the last working user config. Never kill the caller. Never claim the
  running session loaded new files.
- Do not type `auth login`, `auth complete`, `publication plan`, or
  `publication confirm`. Use `account` to sign in (login never uploads) and
  `publish` for a local object. Show an `actor=external` payload once, then
  `task continue`. Do not invent git provenance.
- Use CLI configuration and installation commands. The provider writes the
  harness target; do not replace its work with manual native-file edits.
- Keep exact setup/component versions, proposal and operation identifiers,
  plan digests and preserved-setup references from real responses.
- Default to `authoritative`. Under existing task authority, an `experimental`
  choice stays explicitly labeled. Show `author_verified` and
  `component_verified` independently.
- Keep the control Skill available across setup changes. Change an active
  environment through its staged handoff/restart path.
- On an error or partial result, inspect the actual state and follow recovery.
  A timeout is not proof that no effect occurred. A required browser sign-in
  remains pending until it actually completes.
- Finish with the installed identity, target status, remaining authorization
  and the available recovery reference. Report any unverified part explicitly.
