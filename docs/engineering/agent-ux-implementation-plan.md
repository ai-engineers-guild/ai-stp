---
description: "Target implementation plan for the agent-first CLI: weakest-model loop, shared task engine, and the website-to-native journeys in epic #261."
last_verified: "2026-09-19"
---

# Agent UX implementation plan

This document is a **target execution plan**, not a description of current
behavior. Live requirements remain epic
[ai-stp#261](https://github.com/ai-engineers-guild/ai-stp/issues/261) and
issues #262–#275 plus
[setup-systems#316](https://github.com/NDDev-it-com/setup-systems/issues/316).
This file is the engineering contract for how those issues are implemented
in *this* tree without shrinking acceptance.

Owner goal: after `uv tool install ai-stp-cli` and one pasted initialize
prompt, a Haiku-class agent operates ai-stp. The agent picks an intent,
relays answers, and reports verification. The CLI owns acquisition,
composition, backup, plan, approve, apply, verify, retries, and recovery.

## Checkpoint (2026-09-19)

The agent-first CLI is on
`feat/agent-task-lifecycle` as PR
[#297](https://github.com/ai-engineers-guild/ai-stp/pull/297). This agent
does not merge. Epic #261–#275 stay OPEN. Do not touch colleague issues
(#254, #256, #291, #300).

| Object | Identity |
| --- | --- |
| Branch | `feat/agent-task-lifecycle` at `541d6e14` (includes `4a1d9752` env-bin `bundled_cli()` fix; probe-in-fill was tried and reverted — `--probe` stays opt-in by design) |
| PR | [#297](https://github.com/ai-engineers-guild/ai-stp/pull/297) into `dev`. Not merged; mergeable |
| `origin/dev` at verify | `80db1e9d` (#300). Already merged into the branch; merge-base is `80db1e9d` |
| Released CLI | still `0.0.22`. No PyPI cut |
| Provider kit | `0.2.13` recorded in `tests/golden/provider-kit/identity-ledger.json` |
| Issues | #261–#275 OPEN. setup-systems #316 OPEN. Never close #256. Draft #254: do not touch |
| Haiku 20×5 | overlay 53 pass / 0 fail / 47 unrun. Durable `--fill` restarted with `--docker-image ai-stp-iso:local`; agy capacity 503 at restart. Not a ship gate |

### Gates observed on this host (2026-09-18)

| Gate | Result |
| --- | --- |
| `just docs-static` + `docs-test` + `docs-build` + `docs-regress` | pass (`HOME=/home/rldyourmnd` for mermaid) |
| `just back-static` | pass |
| `just back-test` | 6923 passed, 485 skipped, 4 failed on first full run. Then `test_cli_private_catalog` was patched onto `application.catalog.endpoint` and re-ran green. Left on this host: actionlint SC2015 on private `.github/workflows/branch-policy.yml` (CI skips when actionlint is absent), two bwrap `RTM_NEWADDR` probes |
| `just back-resource` | pass |
| `just back-regress` | pass after Skill canary `task intents --json` |
| `just web-static` | pass |
| `just web-test` | pass |
| `just web-regress` | 224 passed, 8 skipped |
| `just web-feature-profiles` | pass |
| `just security` | pass under bun `1.4.0` |
| Slice 9 Haiku fill | **skipped** (restarted 2026-09-19) |
| focused `pytest tests/unit/test_cli_agy_qualify.py` on `541d6e14` | 44 passed |

### Live CLI

- Root `--help` Commands: **`task` only**. Expert leaves stay invokable, hidden from the dump.
- Eight shipped intents. `cli_version` `0.0.22`.
- Inventory leftover **0**. `component publish` stays `task_pending`.
- `application/` does not import `ai_stp_cli.commands` (ADR-0181).

### Slices vs ship

| Slice | Code | Qualify / ship |
| --- | --- | --- |
| 0 land kernel | on the branch + PR #297 | owner merge into `dev`, not this agent |
| 1–8 | committed on the branch | Haiku overlay 53/100 pass, fill running |
| 9 qualify + promote | runner exists; fill restarted under Docker | no ≥95/100 claim; no wheel promotion; no PyPI |

Last scored Haiku cells (overlay `.tmp/qualify-measured.json`): 5/5 initialize/install-pin/install-open/change/login-skipped/login-idle/publish-private/author; switch 4/5; no-reinit 4/5; publish-public 3/5; relative-root 2/5; eight scenarios at 0/5.

### Remaining to close the epic (do not shrink)

1. **Owner merge** of PR #297 into `dev`. This agent does not merge.
2. **Slice 9 Haiku**: ≥95/100, no scenario <4/5, 5/5 on initialize / install / change / switch. Fill restarted under Docker; agy 503 window open at restart.
3. **Native win/mac** stay `not_run` on this host. Host bwrap `RTM_NEWADDR`; Docker ENFORCED is the isolation path here.
4. **Clean-tree wheel/extra**, promotion of **those** bytes, PyPI **0.0.23** — off until qualify of clean bytes.
5. **setup-systems #316**: do not tag / `publish_public_trees` until released CLI `0.0.23` accepts kit `0.2.13`. Installed `0.0.72` stays.
6. Issue comments with SHA; close only for measured scope. **Never close #256**. Do not touch #254.
7. `component publish` stays `task_pending`. Do not compact `help --agent`. Do not shrink capabilities `command_paths` (REQ-8006).

## 0. How this plan was locked

Re-checked 2026-09-15 against `feat/agent-task-lifecycle` @
`6f19972f0998fa705cb145fc6846d370bd894ca6`, `origin/dev` @
`de37d6f39e2b39f52f671f0f1d4c12ba87d8d248`, live GitHub issues, and the
September 2026 public docs below. Installed wheel, native 7×3 matrix, and
Haiku 20×5 were **not** run.

External practice used (not copied as a second normative system):

| Source | What we take | What we refuse |
| --- | --- | --- |
| Anthropic *Writing effective tools* / advanced tool use (2026) | 3–5 always-loaded tools; prescriptive *when* in descriptions; poka-yoke names (`setup_id` not `id`); tool results truncated (Claude Code 25k default); examples beat schema-only | MCP server, Tool Search over 203 CLI leaves, stuffing every descriptor into context |
| Agent Skills spec + Claude Skills best practices (2026) | `SKILL.md` body under 500 lines; metadata-first; references one level deep; listing description budget (~1.5k chars, ~1–2% context) | A longer Skill that still makes the model choreograph `plan`/`approve`/`apply` |
| Claude Code memory (2026) | User `CLAUDE.md` under ~200 lines; **HTML comments stripped** before injection | Hiding the bridge in an HTML comment |
| Codex `AGENTS.md` (2026) | Global home file is **outside** `project_doc_max_bytes`; project chain is a **cumulative 32 KiB** cap, deepest file truncated first | Writing initialize into a project `AGENTS.md` (steals the budget from nested files) |
| Cursor Rules (2026) | File-based global rules live under the catalogued home `rules/` as `.mdc` with `alwaysApply: true`. Settings “User Rules” are **not a file** | Project `AGENTS.md` (multi-root leak); inventing `~/.cursor/AGENTS.md` (not loaded) |
| Agent-first CLI skill + Claude `ant` CLI (2026) | JSON in/out; stdin JSON merged with flags (flags win); argv not shell-eval; no hidden TTY prompts; semantic exit codes | Interactive `y/n`; colorized-only output |

## 1. Kernel at `6f19972f` (committed tip, not the work tree)

| Object | Identity |
| --- | --- |
| Work branch | `feat/agent-task-lifecycle` @ `6f19972f` |
| `origin/dev` | `de37d6f3` after #277 (typed continuations exist; **no** PyPI cut) |
| Open PRs | [#279](https://github.com/ai-engineers-guild/ai-stp/pull/279) envelope truth; [#280](https://github.com/ai-engineers-guild/ai-stp/pull/280) inspect engine (contains #279) |
| Released CLI | `0.0.22`. Source merge ≠ installed CLI |
| Issues | #261–#275 OPEN, 0 PR comments on #262. setup-systems #316 OPEN. #256 OPEN (never close from this epic). Draft #254 colleague / B2B: do not touch |

Kernel that already exists and must be **evolved**, not replaced:

- Five verbs declared: `task start\|answer\|continue\|status\|cancel`. Schema `cli-task`.
- `application/{inspect,outcome,task}.py`. `SUPPORTED_INTENTS = ("inspect",)`.
- SQLite `agent_task` migration 42. Idempotent start. Revision CAS on write.
- Multi-root `_complete` maps `rolled_back` → `AI_STP_COMPENSATED` (exit 4),
  `recovery_required` → `AI_STP_PARTIAL_OPERATION` (exit 6).
- Canonical Skill is **100 lines / 5630 bytes** (under the 500-line budget).
  The failure is the **17 playbooks**, especially `install.md` steps 4–6
  (`plan` → `approve` → `apply` typed by the model).
- Website `/agents.md` and Skill bootstrap: `doctor --json` then
  `help --agent --json`.
- `help --agent` is a **no-op flag**. Default help is the full **203**
  descriptors. Golden `tests/golden/cli/machine-help.json` and
  `test_cli_registry_fingerprint.py` assert that. Do not flip this in an
  early slice.
- `Continuation.arguments: dict[str, str]`. `continuation_command` joins
  `--k v`; `""` means a flag. No `--input`. Click value types are only
  `string\|boolean\|integer`.
- `capabilities()` embeds `command_paths` for the whole registry. Inspect
  task returns that blob. Claude Code will truncate/waste the 25k tool
  budget on it.
- `TaskView.outcome` is hardcoded `TaskInspectOutcome`. `view_of` will
  throw on a second intent unless the union lands first.
- `payload_document` canonicalizes `{intent}` only. Extra start fields are
  not part of idempotency.
- Capability map: 15 inspect, 40 expert, **148 leftover dumped as `task`**,
  7 named everyday leaves (missing `install approve` / compose / preserve /
  publish / auth). Unlabeled leftover = 136.
- `setup_compose` imports `commands.registry`. `install_transaction`
  imports `commands.install`. `install.py` imports `commands.select`.
- **Single-root `install apply` returns `Answer` (envelope `ok=true`) for
  journal states `failed`, `stale`, `rolled_back`, and `partial`.**
  Multi-root was fixed; this path was not. Extracting install into
  `application.install` without this mapping copies the lie into the task
  engine.
- Login: `POST /auth/device` + token poll only. Does not upload inventory.
- Publication without GitHub already exists: `publication plan` with
  optional `source_binding_id`.
- `project sync apply` stores a pointer receipt. Content upload is
  `project revision push` with `PROJECT_PROJECTION_FIELDS` only.
- Native providers: subprocess JSON v3 (`invocation_v3`). Core ops:
  `backup\|install\|remove\|replace\|restore`. No managed-section op.
- `COMPONENT_TYPES` includes `cli`. Provider `ComponentKind` does **not**.
  The task engine must not assume they are the same list.
- HTTP client already bounds retries: `MAX_ATTEMPTS = 3`. Install apply
  docs already forbid automatic replay of apply (`operation.md`).
- Harness instruction surfaces are already encoded in
  `local/harness_catalog.py`. Initialize must use that catalog, not a new
  table.
- `config init` / `device init` / `doctor` write **no** harness
  instruction files.
- `fork_origin` is component-fork. `preserved_setup` is a complete native
  snapshot bound to a setup identity. Do not invent a third snapshot store.
- `select propose` allows many concurrent sessions; the docstring says
  “the agent decides how many to show.” That is the opposite of one
  justified recommendation.
- `SPEC-080` currently **excludes** install-through-task, website init, and
  the instruction bridge. `SPEC-011` REQ-1106 freezes Skill bootstrap as
  doctor+help. `REQ-1103` keeps plan/apply as separate **commands**.
- `cli_copy.py` has `INSTALL_CLI` and `LOGIN`. There is **no** initialize
  prompt template. Copy buttons are parser-tested
  (`test_cli_copy_templates.py`).

PRs #279/#280 are a kernel. They are not UX-01/02/03 done.

## 2. Locked architecture

### 2.1 Agent-visible surface (poka-yoke)

The agent loads **six** things, not 203:

```text
ai-stp task intents --json     # compact catalog; inspect-class
ai-stp task start
ai-stp task answer
ai-stp task continue
ai-stp task status
ai-stp task cancel
```

Five verbs already exist. `task intents` is additive. `help --agent`
**stays the full registry** until the Skill rewrite ships in the same
wheel (slice 4). Flipping `--agent` early breaks golden/contract tests and
does not help: the installed Skill still tells the model to dump 203
commands.

Intent names are frozen. The **schema enum grows only when that intent is
drained**. `task intents` lists shipped intents only. Vaporware names in
the catalog are how a weak model calls `publish` and gets a validation
error.

| Intent | When the Skill says to use it | CLI owns |
| --- | --- | --- |
| `inspect` | User asks what is broken / what this CLI can do | doctor + **slim** capabilities. No mutation. Completing inspect is success even if doctor is not `ready` |
| `initialize` | First run, or “ai-stp is not in my harness” | Validate the selected executable once; patch the **user/global** instruction surface of the **active** harness only |
| `install` | Put a catalog or local setup/component on a target | Pin or one recommendation; acquire; plan; approve under task authority; apply; native verify |
| `change` | Add/remove/update a member of a **saved** setup | New setup ID + lineage + snapshot; original preserved |
| `switch` | Use another saved setup, or return to last working config | Drift capture; restore user working config; `pending_reload` if the session must restart |
| `author` | Register a directory or create a local object | Bounded import; typed questions; drafts stay on one task |
| `publish` | User said publish/share, with private or public | Existing publication plan path; no GitHub repo required; no fabricated provenance |
| `account` | User said sign in/out or **explicit** sync | Device-code; login never uploads; sync is a separate scoped step |

No `recommend` intent (it is a step inside `install`/`change`). No `login`
intent (it is `blocked` + `actor=external` on the task that needs auth).

Parameter names on intent input use full identity words: `setup_id`,
`setup_version`, `component_id`, `project_root`, `harness_id`. Never `id`.

### 2.2 Loop

```text
task intents --json
  → start --intent I --input {facts} --idempotency-key K --json
    (start drains once; the first envelope is already blocked or completed)
  → loop on envelope.continuations[0]:
        kind=advance, actor=cli
            → exec argv (or in-process continue) until a boundary
        kind=blocked, actor=human
            → ask the user the TaskQuestion once → task answer
        kind=blocked, actor=external
            → show user_code / URL once; later task continue
        kind=blocked, question_id=reload-session
            → tell the user to start a new session; keep task_id
        no continuations + terminal state
            → stop; report payload + verification, not ok alone
  → never: doctor every turn, catalog comparison, digest questions,
           plan/approve/apply typed by the model, retry storms
```

`task start` mints then **drains in-process** once. `task continue`
**drains in-process** until a boundary. Returning to the
model between `install plan` and `install apply` is a bug.

Idempotency key: minted per user-intent instance (UUIDv4 is fine). Same
key + same **canonical input document** returns the same task. A new user
request gets a new key. Natural-language similarity must not reuse a
completed task. Canonical input includes intent **and** the `--input`
body. Same key with a different canonical document is `AI_STP_CONFLICT`.

### 2.3 Transport (evolve #276, do not fork)

Reader-first (`docs/engineering/schema-evolution.md`):

1. Envelope readers accept `arguments` values as JSON
   (`string \| number \| boolean \| string[]`).
2. Additive `argv: list[str]` — the **only** execution form.
3. Additive `actor: human \| agent \| cli \| external`.
4. Producers then emit typed values + `argv`.
5. `continuation_command` is a **quoted display** string for humans/old
   callers. It is never eval input. Tests must round-trip through the
   Click parser, including spaces, Unicode, `""`, repeatables, and
   dash-prefixed values.
6. Terminal results emit **no** continuation. Delete
   `kind=terminal` + `install transaction status`.
7. Agent nested payloads: `--input <file|->`. Stdin JSON merges with
   flags; **flags win** (Claude `ant` 2026). Non-TTY never opens a prompt.
8. `ok`, task `state`, `goal_satisfied`, child operation knowledge, and
   native verification stay independent. `task status` is a read and may
   describe a failed target.

`--json` remains **output** mode (already global). Do not overload it as
the request body.

### 2.4 Shared core vs expert leaves

Click stays a parser (`ADR-0057`). One in-process application layer.
Expert leaves remain for humans, recovery, and scripts. They call the
same services. Skill and `task intents` never list them.

Inventory oracle (replace today’s dump):

| Class | Meaning |
| --- | --- |
| `inspect` | Cheap read |
| `task_covered` | Effect reachable through a **shipped** intent |
| `task_pending` | Everyday leaf, not yet drained. Allowed only while this epic is open. Each intent PR moves its leaves |
| `expert` | Diagnosis / grants / evaluation / attestation / blast-radius. One-line reason in code |
| `obsolete` | Named data-preserving retirement |

Unlabeled leftover is a test failure. Ordinary journeys must not live
only in `expert`: install (including approve), compose, preserve/restore,
import, registry search/acquire, adopt, publication, auth login, config
init, select propose/confirm.

Kind list: `COMPONENT_TYPES`. Native matrix: `HARNESS_IDS` + provider-info
`projection_profile` + `harness_catalog.py`. Never a third list inside
the task engine.

### 2.5 Truthful install outcomes (hard gate before any install intent)

`install.py` `apply` currently `return _view(...)` wrapped in `Answer` when
the journal is `failed`, `stale`, `rolled_back`, or `partial`. Envelope
`ok=true`. A weak model stops.

Map, matching multi-root `_complete` and `SPEC-011` REQ-1132:

| Journal state | Envelope | Code | `goal_satisfied` |
| --- | --- | --- | --- |
| `verified` | `ok=true` | — | true |
| `applied_unverified` | `ok=false` | `AI_STP_PARTIAL_OPERATION` | false |
| `partial` / `recovery_required` | `ok=false` | `AI_STP_PARTIAL_OPERATION` | false |
| `rolled_back` | `ok=false` | `AI_STP_COMPENSATED` | false |
| `failed` / `stale` | `ok=false` | `AI_STP_PRECONDITION_FAILED` or existing mapped code | false |
| `cancelled` | `ok=false` | `AI_STP_CONFLICT` | false |

Doctor remains `ok=true` with failed checks in the payload (inspection
succeeded). Do not “fix” that.

Existing unit tests that treat single-root rollback as a successful
`Answer` are documenting the lie; change them in the same PR as the
mapping.

### 2.6 First product proof

Inspect-on-task is not the owner's proof.

Skill + website rewrite ships in the **same wheel** as all of:

1. Website install command installs the CLI (`uv tool install ai-stp-cli`).
2. Generated initialize prompt → `initialize` → user/global section written
   by the **provider**.
3. New session discovers ai-stp without the paste.
4. Unrelated coding request does not re-run initialize or full diagnostics.
5. `install` of one public setup → independent native verification.
6. Login skipped. Network spy shows no publication/sync/revision-push.

Until that wheel exists, keep current Skill playbooks so 0.0.22-era
behavior is not stranded on an inspect-only surface.

### 2.7 Derived setups

Hard gate for `change` only. Catalog `install` onto a target reuses the
existing coordinator and does **not** mint a new setup ID.

`change`: exactly one new setup stable ID, lineage, original preserved,
`preserved_setup` snapshot of the pre-change native state. Replays and
no-ops do not mint IDs. Drafts inside one `author` task are not
saved-setup mutations. Control-attachment maintenance is not a
saved-setup mutation.

Stores stay distinct:

| Store | Owner |
| --- | --- |
| Portable setup / passport / `content` blobs | Local registry |
| Provider backup (`backup_ref` = `slot-…`) | Native provider disk |
| `preserved_setup` | Setup identity + required `backup_ref` + digest |
| Activation / install journal | `operation_…` rows |
| Shared executable / software ops | Optional provider `software_*` |

### 2.8 Initialize: catalog surfaces, not invented files

Initialize writes the **user/global instruction** row from
`harness_catalog.py` for the **active** harness only. It does not enroll
every detected harness, does not replace the active setup, does not
reinstall the harness program, and does not write **project** instruction
files (epic: works without choosing a project).

| Harness | Catalog global instruction | Constraints |
| --- | --- | --- |
| `claude-code` | Home `CLAUDE.md` | Visible Markdown. HTML comments are stripped. Keep the **section** tiny; do not bloat the whole file past ~200 lines |
| `codex` | Home `AGENTS.md` (`CODEX_HOME`) | Global file is **exempt** from the 32 KiB project cap. Do **not** write project `AGENTS.md` |
| `pi` / `opencode` / `grok-build` | Home `AGENTS.md` | Same: global, preserve existing bytes outside markers |
| `cursor` | Home `rules/` directory (already `evidence=bytes`) | `.mdc` with `alwaysApply: true`. Not Settings User Rules (not a file). Not project `.cursor/rules` |
| `antigravity` | Catalog gap `no_global_instruction` | Do **not** invent a file the product ignores. Discoverability = control Skill + local registry. Initialize records that limitation honestly |

Custom homes / override env vars already live on the catalog
(`CODEX_HOME`, Cursor config root). Respect them.

Section contract (frozen before #316):

- Visible begin/end markers (not HTML comments).
- Byte budget: ≤ 2 KiB, ≤ 40 lines.
- Body is the loop in §2.2 plus `task intents`, not machine-help.
- Idempotent: same digest → no write, task completes, no extra setup.
- Removing the section must not delete the rest of the file.

ai-stp never becomes a second writer of harness finals. Unit tests may
use a fake provider that already declares the optional operation. The
product path may not.

### 2.9 Provider protocol (ADR-0125 order)

Do **not** add a core operation (that breaks every current provider). Add
an **optional** operation name, accepted by the CLI one release before any
provider declares it.

Reader-first:

1. This repo: protocol enum + ignore/accept in `provider-info`.
2. `just back-gen` provider-kit (kit `0.2.13` accepts `instruction_section`
   on `plan_request_fields`).
3. setup-systems #316 implements region patch (preserve-outside-markers,
   custom home, no HTML-comment wrapping) and declares both the optional
   operation and `instruction_section`.
4. Render seven public providers. Do not hand-edit generated trees.
5. CLI sends the operation only to a provider that lists it, and sends
   `--instruction-section` only to a provider that lists that field.
   This tree does step 5 against the remembered chosen or configured
   provider. Live invoke still waits on a bound binary that declares both
   (debug `feat/patch-instruction-region` is not tagged; released
   `0.0.72` does not declare the op) plus enforced isolation.

Until a bound provider declares both, `initialize` against a real harness is `blocked` with a
precise “provider too old” payload, not a silent Python `open()`.

Control attachment identity ≠ user setup. Restore of old setup bytes +
newer attachment = two recorded effects.

### 2.10 Recommendation

Reuse `eligibility` + `select` internals. Change the **agent-facing**
rule:

- Exact `setup_id`+`setup_version` (or component pin) is honored.
- Otherwise the CLI emits **one** justified eligible candidate and
  proceeds unless the effect fork needs a human question.
- Zero eligible → typed refusal, not a catalog dump.
- Popularity is not compatibility.
- Do not open N proposal sessions for the model to compare.

`select propose` as an expert leaf may still create one named proposal;
the task engine must not ask the model to pick among five.

### 2.11 Auth, publish, sync

- Missing auth: `blocked` + `actor=external` + existing device-code
  payload (`user_code`, `verification_uri`). Skill shows it once. No
  tight poll loop (`auth complete` is drained by `continue` with the
  same `MAX_ATTEMPTS` / pending handling already in `auth.py`).
- Login POSTs auth only. Negative test: no `/publications`, no
  `/sync-plans`, no `/revisions`, no catalog PUT.
- `publish` reuses `publication plan` → artifact PUT → `confirm` with
  `source_binding_id=None` and filesystem provenance. SPEC-071 private
  default. No fabricated git history (SPEC-073 stays optional).
- Explicit sync is `account` with a scope field, implemented as today’s
  `project sync` / `revision push`. Never implied by login.
- Worker acceptance receipt ≠ readable published result.

### 2.12 Retries (#272 is policy, not a framework)

Reuse `cloud/client.py` (`MAX_ATTEMPTS=3`). Do not retry apply; recover
from the durable receipt (`install recover`). `continue` that observes
no journal progress twice → `failed` + `AI_STP_DEPENDENCY_UNAVAILABLE`
or a dedicated no-progress code, not another apply. Auth pending is not
retryable (`NEVER_RETRIED` already lists it). No full-suite and no model
eval inside end-user commands.

### 2.13 Skill / website / generation

One declaration of verbs, intent names, and input schemas. Generate:

- CLI summaries
- `schemas/v1` + contracts
- canonical Skill + seven projections + locales
  (`docs_scripts/skill_projections.py`)
- `cli_copy.INITIALIZE_PROMPT` + `/agents.md` route
- golden fixtures + deterministic driver corpus

Target `SKILL.md` body: the loop, hard rules, “call `task intents`”. No
playbook that restates plan/approve/apply. `references/recover.md` stays
for expert recovery (on demand). File references stay one level deep.

`cli_copy` templates must still parse through the real CLI
(`test_cli_copy_templates.py`). The initialize prompt is prose plus one
`task start` line that the parser accepts.

### 2.14 Specs

Keep **one** `SPEC-080`. Do not shrink MUST to match a PR.

- Slice 1: reverse the “install excluded” scope sentence. Add REQs for
  transport, compact intents, truthful single-root mapping. Unshipped
  intents are **not** in the `TaskIntent` enum yet. A contract test
  asserts unknown names are refused.
- `SPEC-011`: REQ-1103 plan/apply remain **expert commands**. The task
  engine drains them in-process under task authority (`ADR-0150`).
  REQ-1106 bootstrap pair becomes `task intents --json` **when the Skill
  rewrite ships**. REQ-1130: unscoped `help --json` remains the full
  registry. REQ-1131: `argv` canonical.
- Extend `ADR-0181` rather than a pile of new ADRs. New ADR only if the
  optional provider operation becomes an architecture rule beyond
  ADR-0125.

### 2.15 Out of scope

Rust CLI, desktop, embedded LLM, daemon, MCP (headless `application/` is
the future adapter). #254 / B2B. #256 F10/R05 / estate (never put
GitHub “close” near #256). Branch-protection changes. PyPI 0.0.23 before
Phase D of the **same** bytes. Closing the epic from a kernel PR.

## 3. Wire sketches (target)

### 3.1 `task intents` (compact)

```json
{
  "schema_version": 1,
  "cli_version": "0.0.23",
  "registry_digest": "sha256:…",
  "intents": [
    {
      "name": "inspect",
      "when": "Call when the user asks what is wrong or what this CLI can do. Do not call as a prelude to every mutation.",
      "input_schema": "urn:ai-stp:schema:v1:cli-task-input-inspect"
    }
  ]
}
```

Shipped intents only. Each `when` is a trigger, not a capability essay.

### 3.2 Start → continue (inspect)

`start` returns `state=planned`, continuation
`argv=["task","continue","--task","task_…","--revision","1","--json"]`.
`continue` runs `doctor`+slim capabilities in-process, `state=completed`,
`goal_satisfied=true`, **no** continuation. Slim capabilities: version,
installation identity, registry digest, schema version, harnesses,
catalog/sync flags, **shipped intent names**. No `command_paths`.

### 3.3 `--input` for `install`

```json
{
  "harness_id": "cursor",
  "project_root": "/abs/path",
  "setup_id": "setup_…",
  "setup_version": "1.4"
}
```

Omit pins → CLI recommends one. Omit `project_root` inside a known
workspace → project scope if the catalog supports it; else **question
once**, never silent global.

### 3.4 `TaskQuestion` (additive fields)

Keep `question_id`, `prompt`, `value_type`, `choices`. Add:

- `recommended`: at most one choice the CLI would take
- `why`: one short sentence
- `actor`: `human` or `external`

### 3.5 Task row (migration 43)

Keep 42. Add nullable indexed columns used for overlap refusal:

`harness_id`, `project_root`, `scope`, `account_id`,
`precondition_digest`.

Child receipts stay in `child_operation_ids_json` (existing
`operation_…` ids). Do not duplicate the install journal.

One running **mutating** task per `(harness_id, project_root, scope)` when
`harness_id` is known. Second start or answer that would collide →
`AI_STP_CONFLICT` with the held `task_id`. Inspect may run concurrently.
Unbound mutating tasks (no harness yet) do not refuse each other until a
harness is bound. Schema 43 stores those columns.

## 4. Continue drain (per intent)

Rules for every intent:

- Compute effects **outside** a long SQLite write; persist receipts
  inside a short transaction (already the inspect pattern).
- Bound inner HTTP with `MAX_ATTEMPTS`.
- On unknown effect: read the original durable receipt before any
  replay.
- Cancel of `planned` is a row update. Cancel after a native write
  triggers the existing compensate path, not a second writer.

| Intent | In-process steps | Boundaries that return to the agent |
| --- | --- | --- |
| `inspect` | doctor + slim capabilities | none (already complete) |
| `initialize` | detect active harness from session/catalog; skip if section digest matches; else provider optional-op | provider too old; missing executable; antigravity limitation |
| `install` | bind context → pin or one recommendation → acquire → plan → approve (task authority) → apply → native status oracle | human scope fork; exact pin unknown; auth; `pending_reload`; compensated/partial |
| `change` | snapshot → compose new identity → install graph | same plus lineage conflict |
| `switch` | capture drift → restore preserved or named setup → verify | `pending_reload`; missing snapshot |
| `author` | validate directory → questions → persist draft on this task | human authoring fields; validation errors |
| `publish` | validate portable object → publication plan → PUT → confirm | auth; visibility choice if omitted; worker receipt vs readable |
| `account` | login begin / complete / logout / explicit sync | device-code wait; never implicit upload |

`pending_reload`: `state=blocked`, `goal_satisfied=false`, question
`reload-session`. Files may already be written. Do not claim the running
process loaded them. Do not kill the caller.

## 5. Gap vs work tree (2026-09-16)

| Area | Work tree | Remaining |
| --- | --- | --- |
| Verbs | 8 declared and drained: inspect, initialize, install, change, author, switch, account, publish | win/mac native cells + Haiku native-bytes (overlay is proxy) |
| Discovery | Additive `task intents`. Skill starts at `task intents --json` | Keep `help --agent` full |
| Continuations | JSON values + `argv` + `actor`; quoted display; continue claims revision; blocked human binds `question-id` and emits `task answer` argv without `value`; Skill executes argv only for `actor=cli`; explicit `argv` wins over missing→help | Keep; no second protocol |
| Inspect payload | Slim orientation, no `command_paths` | — |
| `install apply` | REQ-1132 mapping on single-root and multi-root | — |
| Application | install + change + author + switch + account + publish + coordinator extracted; select/catalog/auth/sync/publication live in `application/`; Click facades; unlabeled leftover = 0 | `component publish` stays `task_pending` |
| Task row | Full-input idempotency; `kind`-discriminated outcome; `task start` drains once; leftover `planned` replay drains; leftover `running` replay joins (no empty-continuation success); same-key insert race joins; continue claims `running`; install child resume; schema 43 overlap columns; one mutating task per bound `(harness_id, project_root, scope)` | — |
| Init | `initialize` + catalog surfaces + optional op; task-engine fake-provider hooks; bound chosen/configured lookup; kit `0.2.13` accepts `instruction_section` and sends `--instruction-section` only when the bound provider declares both; drain `CliFailure` keeps `details.task`, `details.state=failed`, and drops expert `next_actions`. setup-systems kernel on `feat/patch-instruction-region` plan/apply/withdraw preserves `:::begin-ai-stp` / `:::end-ai-stp`; empty first write keeps bytes before markers; argv accepts YAML `---` as the section value; YAML frontmatter survives setup replace/withdraw of the attachment. Live Docker ENFORCED initialize against bound debug cursor/claude/codex/pi/opencode/grok-build writes catalogued surfaces (`alwaysApply` on cursor). Installed `0.0.72` omits the op. Antigravity lists the field and not the op | tag/publish providers only after CLI `0.0.23`; do not install over `0.0.72`; host bwrap denied |
| Qualify | identities hashed; default report all `not_run`; measured overlay cannot fill unrun cells; isolated `agy_qualify` prompt/score covers all 20 names; linux providers on PATH but v3 local phases refuse without network isolation; overlay `isolation` may record `unavailable` without filling native cells; `--native-drive` scores verified + catalogued config-root `tree_digest`; wheel/extra `not_built`; overlay 100 pass on `gpt-oss-120b-medium` (install/change/switch/custom-home/pending-reload 5/5 truthful Docker+Haiku; initialize 5/5 truthful limitation outcome; author/relative/login-idle 5/5 truthful; publish trio 5/5 truthful blocked authorization; login-skipped 5/5 no CLI); wrapper/score path jail; empty-log 503 does not retry; `--probe` is opt-in; `--fill` walks unrun cells one-at-a-time with a 90s gap and does not overwrite scored pass/fail; start-only 503 retries a clean attempt; `--fill` skips a 503 empty-log cell to the next unrun cell; remaining follow-through names are not a verified native-bytes claim; install/change/switch overlay score requires completed+verified (verified start with empty continuations is pass); custom-home overlay score requires completed initialize `wrote` for codex and markers at `CODEX_HOME/AGENTS.md`; relative `--root` is resolved so seed/wrapper exec; those four mutating prompts include `VERIFIED_DRAIN`; opt-in `--docker-image` execs the isolated CLI inside privileged Docker; change loads locally authored embedded members; task-drain failures drop `provider network` and attach `details.state=failed`; harness config roots are not `project_root`; score fails `task answer` without `--value` and `task get`; `FOLLOW_ACTOR` stops when continuations are empty and `actor=human` is not wait; choreography ignores `--value` payloads | native linux-x86_64 7/7 executed under Docker ENFORCED; win/mac `not_run`; wheel/extra from a clean tree |
| Recommend | one first-party `baseline` pin | — |
| Derive | `change` mints setup id + `fork_origin` + `related_setup_ids`; `switch` restores last user `preserved_setup` | — |
| Publish | `publish` drains no-binding publication plan | — |
| Skill/web | generated loop + `cli_copy.INITIALIZE_PROMPT` / `INITIALIZE_START --json`; playbooks intent-first; no transaction-apply / adopt / doctor-prelude / named-plan-leaf choreography; `recover.md` continues an open task before naming `install recover`; Skill text names no flags except the bootstrap pair; Skill forbids inventing `task status` / `task info` | — |
| SPEC-080 | enum of eight drained intents; REQ-8007 start drains once; REQ-8010 human argv; REQ-8020 driver + 503 retry policy; REQ-8021 overlap; REQ-8022 group→intent redirect | Haiku + native qualify |
| Issues | not closed | comment SHA + remaining gap; do not close early |

## 6. Execution slices

Work-branch → PR into `dev` → merge commit → later `dev`→`main`
(`docs/engineering/git-workflow.md`). Do not merge from this plan until
the owner says execute. Do not `--force` `main`/`dev`. Do not touch
draft 254. Focused checks while editing; CI is feedback. No `just check`
inside CLI commands.

Slice status on this work tree:

| Slice | Status |
| --- | --- |
| 0 | Commits on this branch; **not** merged to `origin/dev`. Do not merge from this agent |
| 1–8 | Implemented in the work tree (uncommitted). Live CLI: eight intents, root `--help` is `task` only |
| 9 | Overlay **49 pass / 0 fail / 51 unrun** (2026-09-18). Gates not met (change 2/5, switch 3/5, no wheel, no PyPI). Native linux-x86_64 7/7. win/mac `not_run`. Fill still 1-wide |

Each slice: spec/ADR as in §2.14, `just back-gen` if schemas move,
`just docs-gen` if docs move, i18n for user-visible questions, issue
comment with PR URL + base/head SHA.

### Slice 0 — land the kernel

Merge #279 then #280 (or merge #280 and close #279 as contained).
Comment #262/#263/#264: kernel only. Do not close.

### Slice 1 — truth + transport + compact catalog

Blocks every mutating intent.

Starting points: `envelope.py`, `machine_help.py`, `app.py`,
`application/outcome.py`, `application/task.py`, `commands/install.py`,
`commands/install_transaction.py`, `commands/machine_help.py`,
`test_cli_envelope_truth.py`, `test_cli_install_commands.py`,
`test_cli_capability_map.py` (only if needed for `task intents`
declaration).

Do:

- Single-root apply/recover: unmet goals raise `CliFailure` (§2.5).
- Continuation reader-first: JSON values, `argv`, `actor`.
- Quoted display serializer; parser round-trip tests.
- `--input` on `task start` / `task answer`.
- Declare `task intents`. Keep `help --agent` full.
- Slim inspect outcome (no `command_paths`).
- Drop terminal continuations.
- Idempotency over full canonical input.
- Restore SPEC-080 scope sentence; add transport REQs.
- Protocol test: start→continue→completed for inspect **using emitted
  `argv` only**.

Exit: a script can drive inspect without 203 descriptors and without
shell-join. Rollback is never `ok=true`.

### Slice 2 — honest inventory + extract install service

- Five-class capability oracle. Expert rows have reasons.
- Everyday journeys listed in §2.4 cannot be `expert`.
- Extract `application.install` (plan/approve/apply/status/recover) so
  `commands/install.py` and the future intent share one path. Then the
  coordinator. No nested `ai-stp` process.
- `view_of` outcome becomes a discriminated union **before** the next
  intent is added.

Exit: `component publish` cannot be class `task_covered` until `publish`
ships.

### Slice 3 — initialize contract + optional provider op (parallel #316)

ai-stp:

- Freeze section template + markers + per-harness catalog paths (§2.8).
- Protocol: accept optional operation name (ADR-0125).
- `initialize` intent against fake provider in tests (idempotent,
  preserve-outside-markers, custom home, refuse HTML-comment wrapping,
  antigravity honest limitation).
- Do not rewrite Skill/website yet.

setup-systems #316: kernel on `feat/patch-instruction-region` implements
region patch (markers, preserve-on-setup-write, keep-on-withdraw). Debug
binaries declare the op where the harness has a catalogued global
instruction surface. Do not render/tag public trees until CLI `0.0.23`.

Exit: isolated HOME, all six catalogued instruction harnesses patched and
re-read **against bound debug binaries under Docker ENFORCED** (this
tree, 2026-09-17). Antigravity stays limitation / no op. Real harness
initialize stays `blocked` on released `0.0.72` until a bound binary that
declares both is chosen after the CLI reader ships. Do not tag.

### Slice 4 — context + `install` + Skill/website (first product proof)

- Context resolver: explicit → preference → workspace/session → bounded
  discovery. Unsupported project-local **refuses**, never silent global.
  Ask once when the fork changes the effect.
- `install` drain table in §4. One recommendation. Child `operation_…`
  ids on the task. Compensation mapping from slice 1.
- Deterministic driver on an **isolated** HOME against a candidate
  extra/wheel: initialize (fake or real provider) → install public
  fixture → oracle native bytes + setup id + no-upload spy.
- **Then** Skill rewrite, `cli_copy.INITIALIZE_PROMPT`, `/agents.md`
  route, `SPEC-011` REQ-1106.

Exit: a no-LLM driver completes the owner's first journey. Haiku is
later, against these bytes.

### Slice 5 — `change` (derived setups) + component-on-saved-setup

Hard gate: not the old in-place compose. New setup ID, lineage,
`preserved_setup`, replay/no-op. Individual component onto a saved setup
is `change`, not a hidden overlay.

### Slice 6 — `author`

Hard gate: directory register, typed questions, one task for the draft,
kinds from `COMPONENT_TYPES`, matrix from native surfaces (`rule_for`),
one new setup identity. Not in-place update. Not install.

### Slice 7 — `switch` / restore / handoff

Last **user** working config via `preserved_setup`, not upstream
default. Drift capture. `reload-session` question. Never kill the
caller. Never claim the running process loaded new files.

### Slice 8 — `account` + `publish`

Device-code drain. Negative upload tests on login. Publish via existing
no-binding publication plan. Explicit sync only. Receipt ≠ readable.

### Slice 9 — qualify and promote (#274 / #275)

Candidate wheel + Skill + website + providers. Test **those** artifacts.

1. Deterministic driver full corpus (negative controls, kill
   before/after receipt, concurrent continue).
2. Haiku 4.5, 20×5, ≥95/100, no scenario <4/5, 5/5 on initialize /
   install / change / switch. Stronger models are not used to hide the
   interface.
3. Seven harnesses × Linux x86_64, Windows x86_64, macOS arm64. Missing
   cells stay `not run`.
4. Promote the same bytes. Distinguish: source merged, server deployed,
   CLI released, CLI installed, native files applied, session loaded.

Close issues only for measured scope.

## 7. Haiku corpus (20)

Core (must 5/5):

1. Fresh machine: website install line → initialize prompt → new session
   discovers ai-stp without paste.
2. Unrelated coding task after init does not re-run initialize/doctor.
3. Install exact public setup pin; native oracle matches.
4. Install without pin; CLI picks one; no catalog quiz.
5. `change` add component; original setup id still restorable.
6. Switch back to last working config (`preserved_setup`), not upstream
   default.
7. Unsupported project-local refuses (no silent global).
8. Login skipped; network spy clean.
9. Login then idle: still no upload.
10. Explicit private publish of a local object; no GitHub repo.
11. Explicit public publish; provenance filesystem, not invented git.
12. Directory `author` of one component; one setup identity.
13. Compensated install: envelope not `ok`; goal not satisfied; no
    retry-apply.
14. Kill after apply, before verify: recover, not duplicate.
15. Concurrent `continue` on one revision: one winner.
16. `pending_reload` not reported as loaded.
17. Auth-required publish: one user_code, no poll storm.
18. Antigravity initialize: honest limitation, no fake global file.
19. Custom `CODEX_HOME` / Cursor home: section lands there.
20. Expert recovery: Skill does not dump 203; `task intents` +
    `recover.md` on demand is enough to reach `install recover`.

Hard fail regardless of score: false success, unintended upload, secret
in envelope/log, unrelated config loss, cross-harness write, duplicate
side effect, unsafe replay.

## 8. Issue close table

| Issue | Close when |
| --- | --- |
| #262 | Five-class oracle; leftover unlabeled = 0; everyday journeys have services |
| #263 | Transport + single-root truth + `--input` + argv round-trip |
| #264 | Engine drains initialize+install (later intents as they ship); binding+CAS |
| #265 | User/global section + new-session test + no project required |
| #266 | Context/scope/one-recommendation; no silent global |
| #267 | `author` |
| #268 | Derived setup identity + snapshot + no duplicate IDs |
| #269 | Setup and component through task; native verify |
| #270 | Switch/restore/`reload-session` |
| #271 | Login ≠ upload; explicit publish/sync |
| #272 | Bounds measured on journeys (reuse existing HTTP/apply policy) |
| #273 / ss#316 | Optional op + rendered providers; no hand-edit of generated trees |
| #274 | Driver + Haiku + native cells with identities |
| #275 | Same bytes on website/Skill/wheel/providers |
| #261 | All of the above |
| #256 | Never from this epic |

## 9. Risks

- Copying `install.py` into `application/` **before** §2.5 mapping.
- Compact `help --agent` in slice 1 (golden + old Skill).
- Project `AGENTS.md` for Codex initialize (32 KiB cumulative, leaf
  truncated).
- HTML-comment Claude section (stripped).
- Cursor Settings User Rules (not a file) or project `.cursor/rules`.
- Inventing antigravity global instruction.
- Python `open()` of harness files (violates provider write boundary).
- Adding a **core** provider operation (breaks current binaries).
- `TaskInspectOutcome` left as the only outcome type.
- Idempotency over the full canonical input document (intent + `--input`).
- Skill rewrite before install exists.
- Owner's live `~/.claude` / `~/.cursor` as a test target.
- Closing #262 because inspect exists.

## 10. Rollback

Revert the `dev` merge commit. Additive envelope fields: old readers
ignore. `agent_task` rows: older CLIs ignore extra columns. Failed
native apply compensates through the existing coordinator. Initialize
must be able to skip/remove its marked section without deleting the rest
of the instruction file. Provider optional-op: old providers simply do
not declare it.

## 11. First action when execution is approved

1. Re-read this file against `HEAD` and the work tree (they have moved).
2. Slice 0 remains an owner merge of this branch into `origin/dev`.
3. Keep #254, #256 F10/R05, and PyPI 0.0.23 off the branch until slice 9
   qualify of **clean** bytes.
4. Do not mark native Linux cells `pass` without network isolation.
   Privileged Docker ENFORCED (bwrap) is isolation for those cells; the
   host overlay stays `unavailable` while this host's bwrap is denied.
5. Do not close GitHub issues from a dirty tree.
