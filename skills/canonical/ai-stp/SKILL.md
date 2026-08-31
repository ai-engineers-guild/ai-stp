---
name: ai-stp
description: Manage local setups, passports, providers, and cloud features through the ai-stp CLI.
---

# ai_stp

## Use this Skill when

- preparing a harness for a user or project;
- viewing or changing a developer passport;
- signing in to the platform or checking sign-in state;
- finding an object in the public catalog or viewing its versions;
- selecting, composing, installing, checking, updating, or restoring a setup.

## Start here

1. Run `ai-stp doctor --json` and read the installation state.
2. Run `ai-stp help --agent --json` and take the command list, mutation classes,
   confirmation rules, and schema links from it.
3. Call only the commands returned by machine help.

The command list is not repeated here. It lives in the CLI registry, and a copy
in this file would drift from the implementation on its first change. For the
same reason, this file has no step-by-step routes with exact flags: parameters
come from the installed version's descriptor, not from this text.

You assemble the passport: the CLI discovers facts deterministically, you
interpret them and complete the passport, and the user confirms disputed facts.
`ai_stp` does not call a model itself.

## Workflows

A workflow is a shape of work, not a list of calls. Get concrete commands and
parameters from machine help each time.

**Observe → select → effect → verify.** First, read commands build the picture:
installation state, configuration, available harnesses, and tree contents. Then
select one exact object using an identifier from the previous structured response,
not an invented name. Run the mutating command. Finally, verify the result with a
separate read command instead of inferring it from the exit code.

**Select → plan → approve → apply → state.** Selection produces a snapshot and a
proposal; the plan turns the proposal into an exact, checkable effect with a
digest; approval binds the decision to that digest; apply executes only the
approved operation; state is read from the actual target. Nothing changes
silently between plan and apply: if the CLI reports a stale plan, build a new one
and obtain the decision again.

**Uncertain outcome → actual effect → recovery.** After an unconfirmed timeout or
partial result, first establish what actually happened, then choose the CLI's
proposed recovery action. Repeating apply "for synchronization" is not recovery.

**Daily read-only pass.** Read installation state, sign-in state, operation state,
and the state of every managed target. Run a mutating command only when status
itself proposes that action.

## Reading responses

Every `--json` command prints exactly one object. With `ok: true`, the result is
in `data`; `warnings` may contain information to show the user without making the
call unsuccessful. With `ok: false`, `error.code` contains a stable code from the
closed registry, and `next_actions` names a sensible next step.

For an error, find `error.code` in `error_codes` from machine help and follow its
`handling`, together with the response's `retryable` and `next_actions`. Do not
choose an action from the process exit class alone: one class can include a
conflict, a stale plan, or a request for a user decision. Retry only when
`retryable: true`; after an unconfirmed timeout, first check the actual effect
through the proposed status or recovery command.

## Making decisions

The user's task defines the authority boundary. If the user asked to prepare,
install, update, or repair a setup, perform the local reversible steps included
in that task in sequence without asking again before each one. Ask only when
something outside the task appears.

`mutability` and `confirmation` answer different questions. The first describes
the command's effect; the second describes which machine token proves a decision.
`confirmation: none` only means that no such token is required; it does not turn a
mutation into a read or imply user consent.

- `read` only observes; run it without asking when the user's request does not
  restrict reading.
- `plan` creates a checkable plan or short-lived snapshot without changing the
  target. Use it to get the exact subject of a decision.
- `apply` changes state. Run it when the current request already authorizes that
  change; ask separately only when the effect exceeds the request.
- `destructive` always requires a separate decision immediately before the call,
  even when the user authorized surrounding work earlier.

A separate user decision is required only when an unresolved choice changes the
  result; an object becomes public or its access rights change; a primary version
  line is created; credentials or an account are linked; data, a target, or a
  backup is deleted without a recovery path; an unrequested external Git or
  deployment action is performed; or an `experimental` or unverified-author
  object enters the composition.

For `explicit_flag`, first obtain the decision, then find the required parameter
in the command descriptor and pass it explicitly. For `plan_digest`, first run
the named plan command, show the user the effect and `required_authorization`,
obtain the decision, and pass the exact digest of the unchanged plan to apply. Do
not calculate the digest yourself. If the CLI reports a stale or changed plan,
build a new one, show the difference again, and request a new decision.

Digest checks, precondition checks, and idempotency are always required. They are
mechanical protection for the operation; perform them without a new question
while the meaning and scope of the effect are unchanged. They prove that the
approved effect is the one being executed.

`next_actions` is an ordered hint, not permission. Before every next call, check
its descriptor, availability, effect, and confirmation requirement again.

## Traps

These distinctions are not encoded in command names, and getting them wrong can
look like success.

- Read harness availability from `surface`, `version_source`, and `diagnostic`,
  not from the `version` string: on Windows, the version may come from restricted
  package metadata after a shim fails to start.
- `state: available` with an empty `installations` means "supported by the build,
  but not installed." This is especially common for Pi; do not call it installed.
- An accepted local passport means known provenance and owner consent. It does
  not mean publish-ready, platform-verified, or suitable for the public catalog.
- `ready: true` for passport validation means only local structural completeness
  of an exact revision. It is not permission for a cloud write.
- A provider release signature does not prove compatibility. Both release trust
  and conformance are required.
- Only the catalog command intended for offline closure supplies its bytes. An
  object key alone is not authority and must not be fetched directly.
- `init` is not a universal retry: read the error code and `next_actions` first.
- Local state changes only through commands. Do not edit XDG files directly.
- In browser device flow, show the user the verification URL and code; do not
  approve the account for them.

## Rules

- Do not guess flags: take them from `ai-stp help --agent --json`.
- Do not call a command absent from machine help, even if it seems obvious.
- Before every call, inspect `mutability` and `confirmation` and apply the
  algorithm above.
- Do not bypass mechanical constraints.
- In `project discover`, treat the list as exhaustive only when
  `complete: true`; when it is `false`, show `diagnostics`, narrow the root or
  fix access, and repeat the read command instead of registering candidates
  automatically.
- In `component discover`, distinguish `candidate_id` from the logical Component
  id: the first stably addresses a read-only finding, while the second appears
  only after explicit adoption. To explain classification, show `layout_source`.
  Call a GitHub origin exact only with `provenance.kind: github` and
  `state: exact`; a cache directory name is not evidence. Do not call a Pi Git
  checkout enabled or clean: discovery does not prove that. Show `diagnostics`
  before selection. Do not assign a shared path with `harness_id: null` to one
  harness yourself.
- By default use only the `authoritative` line. Request the `experimental` line
  with an explicit consent signal and show it in a separate section.
- Never move an `experimental` object into an automatic composition.
- Do not call an owned or exactly pinned object platform-confirmed.
- Distinguish `author_verified` and `component_verified` and show them separately.
- A response with `source: cache` describes the past: show `checked_at` with it
  and do not present it as current cloud state.
- When web navigation is needed, use the canonical link and structured
  `cli_argv` from the `link web` read command. Do not construct routes manually,
  add a token or device ID, or treat a link as proof of access.
- Do not change a harness target directly.
- Do not read environment variable values; report only whether a named variable
  is set or missing.
- Never pass a password, token, or secret in arguments, the environment, or logs.
  Sign-in happens in the browser, and the CLI does not see those values.
- Before approving an installation, explain `required_authorization` from the
  `install plan` result. After native setup, call `target status` with the same
  provider and trust only `pending_authorization`; do not infer readiness from a
  successful apply, a present secret, or the user's words, and do not repeat apply
  to finish sign-in.
- Stop and show `next_actions` after a partial result or error.
- Do not delete this controlling Skill together with a user setup.

## Availability boundary

Do not determine feature availability from this Skill or product documentation.
The only executable source is machine help for the currently installed version.
If the required command is absent, do not substitute a similar action or change a
target directly: report the missing capability and show the available
`next_actions`.
