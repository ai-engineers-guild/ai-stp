---
title: "Select a setup"
description: "Eligibility, proposal, reports, graph, bundle, and confirmation."
---

# Select a setup

Selection answers which candidates a harness may be composed from, records
one proposal, and freezes that proposal as a private setup version. It
creates no target. The provider writes native state later, through
[Install](install.md).

The agent may help choose members. It may not bypass mechanical eligibility,
access, or safety constraints. An empty admissible list with reasons beside
it is an honest answer, not a crash.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp select eligibility` | `read` | `none` | which candidates one harness may use, and why each refusal happened |
| `ai-stp select eligibility-matrix` | `read` | `none` | where one object may be composed, for every supported harness |
| `ai-stp select impact` | `read` | `none` | compare context, token cost, and capabilities of exact local versions |
| `ai-stp select blast-radius` | `read` | `none` | local setup, project, device, and target references to a component |
| `ai-stp select propose` | `plan` | `none` | record one composition proposal; no version, no target |
| `ai-stp select confirm` | `apply` | `none` | freeze one proposal as a private setup version, trace, and pin |
| `ai-stp select cancel` | `apply` | `none` | close one proposal without creating a version |
| `ai-stp select graph` | `read` | `none` | resolve the exact dependency closure, or name every reason it cannot |
| `ai-stp select reports` | `read` | `none` | what is chosen, what conflicts, what is lost |
| `ai-stp select bundle` | `read` | `none` | compile the deterministic package; write to no target |
| `ai-stp select session` | `read` | `none` | open proposals for one project and harness, and the version selected |

`--json` is global. Always pass it. `select confirm` has `confirmation:
none`: naming `--proposal` **is** the decision. There is no `--confirm`.

## Eligibility

```bash
ai-stp select eligibility --harness codex --json
ai-stp select eligibility --harness codex --project . --json
ai-stp select eligibility --harness codex --include-unverified --json
ai-stp select eligibility --harness codex --for-redistribution --json
```

`--harness` is required. `--project` names the project root whose facts the
target is built from. `--include-unverified` consents to consider unverified
candidates **for this command only**. It is never stored, and it is never
enough to select one automatically. `--for-redistribution` applies
redistribution rights because the composition is meant to be redistributed.

Success fields: `harness_id`, `harness_version`, `os`, `arch`,
`admissible_count`, `auto_selectable_count`, `candidates`, `capabilities`,
`capability_vocabulary_version`. `admissible_count: 0` with refusals listed
is success.

## Eligibility matrix

```bash
ai-stp select eligibility-matrix --json
ai-stp select eligibility-matrix --harness codex --harness claude-code --json
```

`--harness` is repeatable. Omit it to cover every supported harness. The
other flags match `eligibility`.

## Impact and blast radius

Impact compares exact local setup versions. Blast radius lists local
references to one component version.

```bash
ai-stp select impact \
  --setup-id <setup_id> \
  --setup-version 1.0 \
  --json

ai-stp select impact \
  --setup-id <setup_id> \
  --setup-version 1.1 \
  --against-setup-id <setup_id> \
  --against-setup-version 1.0 \
  --tokenizer-profile ai-stp:utf8-bytes/1 \
  --json

ai-stp select blast-radius \
  --component-id <component_id> \
  --component-version 1.0 \
  --scenario update \
  --json
```

`--tokenizer-profile` is `ai-stp:utf8-bytes/1` or
`ai-stp:unicode-chars-div4/1`. `--price-profile` is an explicit local
token-price JSON file. `--project-id` uses that project's installed or
selected setup as the baseline when `--against-setup-id` is absent.
`--scenario` is one of `update`, `deprecation`, `blocked`,
`expired_evidence`, `advisory`.

## Propose, session, confirm, cancel

A proposal is a short-lived, exact session object. It expires. Confirming
it freezes a private setup version. Cancelling it creates nothing.

`--member` is repeatable, each value `<stable_id>@<X.Y>`. `--empty` composes
a setup that projects no files. `--empty` and `--member` refuse together.

```bash
ai-stp select session --harness codex --project . --json

ai-stp select propose \
  --harness codex \
  --project . \
  --member component_...@1.0 \
  --member component_...@2.1 \
  --json

ai-stp select confirm --proposal <proposal_id> --json
ai-stp select cancel --proposal <proposal_id> --json
```

Propose returns a session with `proposal_id`, `state` (`open`, `confirmed`,
`cancelled`, `expired`), `members`, `harness_id`, `project_id`,
`created_at`, `expires_at`, `snapshot`. Confirm returns `created`,
`stable_id`, `version`, `revision_id`, `state` (`pending_install` or
`installed`), `trace`. A repeat confirm of the same proposal is success:
read `created` to tell "this call made it" from "it was already made".

## Graph, reports, bundle

```bash
ai-stp select graph --proposal <proposal_id> --json
ai-stp select graph --member component_...@1.0 --json

ai-stp select reports --harness codex --proposal <proposal_id> --json

ai-stp select bundle --harness codex --proposal <proposal_id> --json
ai-stp select bundle \
  --harness codex \
  --proposal <proposal_id> \
  --target <absolute-dir> \
  --scope project \
  --json
```

`graph` takes either `--proposal` or repeatable `--member`, not a mix you
invent. Each node has `stable_id`, `version`, `passport_digest`,
`revision_id`, `depth`, `requires`.

`reports` needs `--harness` and `--proposal`. `--project` is the project
root whose facts the target is built from.

`bundle` compiles bytes and a manifest. It is a `read`: `ADR-0012` gives
the write to the provider. `--scope` is `global` (default), `project`, or
`user_root`. `--target` is required when a member contributes a key to a
file the provider already owns: those current bytes exist only on the
target. If `compiled` is false, `digest` and `files` are empty and
`refusals` names every reason.

## Happy path

```text
select eligibility --harness <id> --project .
→ select propose --harness <id> --member <id>@<X.Y>
→ select reports --harness <id> --proposal <proposal>
→ select graph --proposal <proposal>
→ select confirm --proposal <proposal>
→ install plan --proposal <proposal> --provider <exe> …
```

Read `select session` any time you need the open proposal and the selected
version for that pair.

## Named success fields

| Command | Fields to read |
| --- | --- |
| `eligibility` | `admissible_count`, `auto_selectable_count`, `candidates` |
| `propose` / `session` / `cancel` | `proposal_id`, `state`, `members`, `expires_at` |
| `confirm` | `created`, `stable_id`, `version`, `revision_id`, `state` |
| `graph` | nodes with `stable_id`, `version`, `passport_digest` |
| `bundle` | `compiled`, `digest` / `artifact_digest`, `refusals` |
| `impact` | the compared versions and cost fields |
| `blast-radius` | referencing setups, projects, devices, targets |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | `--harness` missing, or `--member` with `--empty` | correct the request |
| `AI_STP_NOT_FOUND` | the proposal, setup, or component is unknown | `select session` or `component find` |
| `AI_STP_USER_DECISION_REQUIRED` | unverified candidates need explicit consent | `--include-unverified` on eligibility, then a human choice |
| `AI_STP_PRECONDITION_FAILED` | the proposal expired or is not `open` | `propose` again; do not confirm an expired id |
| `AI_STP_CONFLICT` | the session already moved | `select session`, then act on the current proposal |
| `admissible_count: 0` | nothing may be composed for that harness | read each candidate's refusal; do not invent a member |
| `compiled: false` | the bundle could not be built | read `refusals`; do not install a half package |
| inventing `--confirm` on confirm | that flag is not declared | `--proposal` is the confirmation |

`--include-unverified` never becomes stored consent. Stored consent is
[Consent](consent.md). Experimental objects still need that consent before
install.

## Related links

- [Install](install.md)
- [Setup commands](setup.md)
- [Component commands](component.md)
- [Registry](registry.md)
- [Consent](consent.md)
- [Setups](../setups/index.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups selection commands so a person can find them. The
installed CLI is the source of flags, schemas, and `next_actions`. If this
page and the CLI disagree, follow the CLI.
