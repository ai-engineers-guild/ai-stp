---
description: "SPEC-080: Headless CLI application services, capability inventory, and the agent task contract."
last_verified: "2026-09-24"
---

# SPEC-080: CLI agent task contract

## Purpose

Give the coding agent one headless application core: Click stays a parser,
expert commands and the task engine call the same in-process services, and
every declared leaf is classified so everyday journeys are not trapped behind
an expert-only vocabulary.

## Scope

Includes the application-service boundary, the five-class inventory of
every declared command, the declared `task` lifecycle, compact intent
discovery, continuation transport, `--input`, and the rule that the task
engine must not reach another command through a nested process. Envelope
truth for unmet mutating goals is owned by `SPEC-011` `REQ-1132` and
`SPEC-058` `REQ-5809`; this specification names that those services are the
shared owner, including single-root `install apply` and `install resume`.

Closed intent names are `inspect`, `initialize`, `install`, `change`,
`switch`, `author`, `publish`, and `account`. The `TaskIntent` schema enum
grows only when that intent is drained. `task intents` lists shipped intents
only. Unshipped names are refused at `task start`.

The drained intents are `inspect`, `initialize`, `install`, `change`,
`author`, `switch`, `account`, and `publish`. `inspect` drains
`doctor` and slim orientation through `application.inspect`. `initialize` writes
the active harness user-global instruction section through the provider optional
operation `patch_instruction_region`; until a provider declares that
operation the task stays blocked, and `antigravity` completes with the
catalog limitation `no_global_instruction`. `install` drains
`application.install` plan, task-authority approve, and apply in-process;
omitted pins become one justified first-party `baseline` pin for the harness,
not a catalog quiz. If no justified pin exists, one `setup-ref` question. `change`
drains a member add or remove on a saved setup into a **new** setup identity,
records `fork_origin` and `related_setup_ids` to the source, and then installs
the derived pin. The source setup id is not overwritten. A member set that
already matches is a no-op identity (no mint) and still installs that pin.
Replays of the same owner and delta reuse the derived id. Embedded members retain
their sealed passport, snapshot and artifact in the derived definition; a change
does not promote them into independently published catalog components. `author` registers one
directory as one embedded component and one new setup identity; kinds come from
`COMPONENT_TYPES` filtered by native surfaces; drafts are not saved-setup
mutations and are not installed. `switch` restores the last user
`preserved_setup` for the target, never an upstream catalog pin; it captures
current drift as a leftover, restores through the provider, then blocks on
`reload-session`. It never kills the caller and never claims `session_loaded`.
`account` drains device-code login, logout, and explicit sync. Login POSTs auth
only and never uploads. `AI_STP_AUTHORIZATION_PENDING` re-blocks with
`actor=external`; declined and expired fail the task. `publish` reuses the
no-binding publication plan (`source_binding_id` absent, filesystem provenance,
private default). Confirming a plan is not a readable catalog result unless
plan `state` is `published`. B2B/enterprise surfaces, estate-release F10/R05,
a CLI language rewrite, and a PyPI CLI cut are excluded.

## Terms

- `application service` — an in-process function that performs one domain
  effect or inspection. Handlers and the task engine call it. It does not parse
  argv and does not start another CLI process to reach another service.
- `inspect` — a cheap orientation command. Reading it does not mutate a
  target, journal, or account. Creating a durable task may create the local
  registry so the task can be stored.
- `task_covered` — an effect already reachable through a shipped intent,
  including the five lifecycle commands that drive those intents.
- `task_pending` — an everyday leaf not yet drained. Allowed only while this
  epic is open. Everyday journeys remain callable expert-shaped leaves until
  an intent owns them.
- `expert` — a leaf that stays a leaf: diagnosis, grants, evaluation,
  attestation, and blast-radius control. Everyday journeys must not live only
  here. Each expert row carries a one-line reason in `application.inventory`.
- `obsolete` — a named, data-preserving retirement. None are classified today.
- `task engine` — `task intents`, `task start`, `answer`, `continue`,
  `status`, `cancel`, and `list`. It persists a `task_…` object, is
  idempotent on start, and continues by matching revision. There is no
  machine-global current task. `task intents` and `task list` are
  inspect-class and do not mint a task.

## Requirements

- `REQ-8001`: Domain work shared by expert commands and the task engine lives
  in in-process application services. Click remains a parser (`ADR-0057`). A
  service does not start another CLI process to reach another service.
- `REQ-8002`: Every declared leaf is classified exactly once as `inspect`,
  `task_covered`, `task_pending`, `expert`, or `obsolete`. The inventory test
  is the oracle. Unlabeled leftover fails. Everyday install (including
  approve), compose, preserve/restore, import, registry search/acquire, adopt,
  publication, auth login, config init, and select propose/confirm must not be
  `expert`. `component publish` is not `task_covered` until `publish` ships.
- `REQ-8003`: Paths `task start`, `task answer`, `task continue`, `task
  status`, and `task cancel` are declared and run. Their result schema is
  `cli-task`. Path `task intents` is declared inspect-class; its result
  schema is `cli-task-intents`.
- `REQ-8004`: Expert commands remain for diagnosis and exceptional control.
  They call the same application services the task engine calls. Duplicated
  business logic beside a service is refused.
- `REQ-8005`: A task object uses the `task_…` identifier prefix. Envelope
  `operation_id` remains an `operation_…` receipt or null. Multi-root
  transaction ids already minted as `operation_…` under `SPEC-058` stay that
  prefix.
- `REQ-8006`: Intent `inspect` drains `application.inspect.doctor` and
  `application.inspect.orientation`. Orientation carries version,
  installation identity, registry digest, schema version, harnesses,
  catalog/sync flags, and shipped intent names. It does not carry
  `command_paths`. Expert `doctor` returns the same doctor model at the same
  moment. Expert `capabilities` remains the full model including
  `command_paths`. Completing inspect satisfies the task goal even when the
  doctor report is not `ready`.
- `REQ-8007`: `task start` is idempotent on the pair of `idempotency-key` and
  the canonical document of intent plus `--input` body. Keys use the shared
  HTTP-contract pattern: 16 to 128 ASCII letters, digits, `.`, `_`, `~`, or
  `-`. Start help names that constraint and the requirement to reuse a key
  only for the same request. An invalid key is refused before task creation;
  its error names the field and pattern without echoing the rejected value
  and points to scoped `task start` help. Drain may enrich
  `payload_json` with checkpoint facts (switch restore ids, account device
  code). Replay of the original `--input` still joins that row; only a
  contradictory user key is `AI_STP_CONFLICT`. After minting, start
  drains once so the first envelope is blocked, completed, or a typed
  failure with `details.task` and `details.state=failed`; clients do not
  need a no-op continue to see questions.   A replay of start on a leftover `planned` row drains that row.
  A replay of start on a `running` row waits for that row to leave `running`
  and returns the settled or blocked view; it must not return `state=running`
  with empty continuations. If the wait expires, start continues that revision.
  A concurrent start that loses the idempotency unique index joins that row
  instead of answering overlap `AI_STP_CONFLICT`.
  `continue`, `answer`, and `cancel` require the current revision. Status
  names the task id; the process does not hold a current task. A successful
  `task status` may describe a failed, cancelled, or compensated target.
  An unexpected interruption while answering a question retains the running
  revision and emits its `task continue` continuation, as an interrupted
  explicit continue does. Reading a running task also emits that continuation
  without performing any work. A replay after persistence reuses the held
  immutable result.
- `REQ-8008`: Advancing a task calls named application services for that
  intent. It does not look up an arbitrary expert leaf in the command
  registry and run it. `application/` does not import `ai_stp_cli.commands`.
  Click handlers import the services.
- `REQ-8009`: `task intents` lists shipped intents only, each with a
  when-to-call trigger, an input schema urn, and `input_fields` — a flat
  name/required/type/choices list derived from the same validation model, so
  choosing an intent and shaping its input take one call. Unshipped intent
  names are absent from the catalog and refused at start with a `cli`
  continuation whose argv is `task intents --json`. The envelope does not
  send `help --path task`.
- `REQ-8010`: Envelope `continuations` carry JSON argument values, executable
  `argv`, and `actor`. `continuation_command` is a quoted display string and
  is never eval input. A terminal outcome emits no continuation. Inspect
  start completes in the first envelope. A blocked human question binds
  `question-id` and leaves `value` missing; argv is
  `task answer` without that value (`REQ-1131`).
  The control Skill distinguishes a harness shell task handle from an ai-stp
  task id. If the shell tool yields before stdout is available, the agent
  retrieves its completed output before another CLI invocation; a timer or
  shell-task status does not establish a CLI outcome.
- `REQ-8011`: `task start` and `task answer` accept `--input <file|->`. The
  file or stdin is a JSON or YAML object parsed into the same typed model;
  unreadable paths and invalid UTF-8 return a validation error naming the
  file-or-stdin interface and scoped start help, without echoing the supplied
  input locator. An inline JSON argument remains a refused file locator.
  Duplicate keys are refused rather than last-wins, in either spelling. Flags
  win over keys
  in that object. Inspect rejects a non-empty input object. A schema
  validation refusal is `AI_STP_VALIDATION_ERROR` whose `details.fields`
  carries the comma-joined rejected field names, whose `details.errors` is an
  RFC 9457 `errors[]` list — `{pointer, issue, detail}` entries with a JSON
  Pointer into the input, the pydantic violation type, and pydantic's own
  constraint detail; rejected values never appear — whose `details.schema`
  names the input schema urn, and which carries a `cli` continuation to
  `schema show --id <that urn>`. Input models declare the formats the drain
  enforces — stable ids carry `stable_id_pattern` and versions the `X.Y`
  pattern — so a malformed value is refused at the boundary, not discovered
  as a failed task row.
- `REQ-8012`: Single-root `install apply` and `install resume` map unmet
  journal states the same way multi-root `_complete` does: compensation is
  `AI_STP_COMPENSATED`, recovery-required and partial are
  `AI_STP_PARTIAL_OPERATION`, and envelope `ok` is reserved for a completed
  install.
- `REQ-8013`: Intent `initialize` drains `application.initialize`. It writes
  only the catalogued user-global instruction surface of one harness. The
  section uses visible begin/end markers, stays within 2 KiB and 40 lines,
  and never uses HTML comments. `ai-stp` does not open harness finals;
  writing is the optional provider operation `patch_instruction_region`. A
  provider that does not declare that operation blocks with
  `actor=external`. `antigravity` completes with limitation
  `no_global_instruction`. A catalogued whole-harness `root_override`
  (`CODEX_HOME`, `PI_CODING_AGENT_DIR`, `OPENCODE_CONFIG_DIR`, `GROK_HOME`)
  is the resolved instruction root. `CURSOR_CONFIG_DIR` moves only
  `cli-config.json`; cursor instruction stays under `~/.cursor/rules`.
  Bytes outside the markers are preserved. The same
  section digest is a no-write completion. When drain kwargs are omitted, a
  non-empty `provider_operations` hook still selects `patch_via_provider` so
  the task engine can complete through a fake provider. Production looks up
  the remembered chosen or configured provider only and stays blocked until
  that provider declares both `patch_instruction_region` and
  `instruction_section`. This build accepts `instruction_section` on
  `plan_request_fields` and does not send `--instruction-section` until a
  provider declares that field (`ADR-0125`). Isolation refusals are
  `AI_STP_DEPENDENCY_UNAVAILABLE` and drop expert `next_actions` such as
  `provider network`. `provider-too-old` is not device-code: the agent
  reports it and does not start `account` or tight-loop `task continue`
  until the bound provider declares both fields.
- `REQ-8014`: Intent `install` drains `application.install` plan, approve
  under task authority, and apply in one `task continue`. The model does not
  type those expert leaves. Omitted `setup_id`/`setup_version` becomes one
  justified first-party `baseline` pin for the harness, acquired in-process.
  Only omission of both fields selects that baseline. Supplying either field
  alone blocks on `setup-ref` until the exact pair is known. An exact setup
  already held under the current owner's identity proceeds to the same
  checked install plan without fetching it from the public catalog. A missing
  version or another owner's setup still uses catalog acquisition; local
  ownership does not bypass graph, artifact, compatibility or provider checks.
  If no justified pin exists, one `setup-ref` question. The CLI does not quiz
  the catalog. Omitted `project_root` is one absolute-path question.
  A catalogued harness config directory (or a path inside one) is not a
  project root; drain asks `project-root` again.
  Unmet apply goals remain `CliFailure` and the task `state` is `failed`.
  A missing developer, device, or project passport is minted in-process
  before plan; the model does not type `project passport` or
  `passport developer init`. Plan receives the catalogued harness config
  root as `target`, creating that directory if it is missing. Drain failures
  keep `install recover` / task-lifecycle `next_actions` and drop expert
  leaves such as `provider network`.
  A continue claims the current revision (`state=running`) before effects so
  a concurrent continue on the same revision is `AI_STP_CONFLICT`. After plan
  the engine records the child operation id; a later continue of that task
  advances the held operation from its journal state — unfinished resumes,
  an approved plan applies, a planned one approves and applies, and an
  already-settled one is read back as its own answer — instead of planning a
  second one.
- `REQ-8015`: Intent `change` drains `application.change`. It asks harness,
  source pin, component pin, and project root at most once each. Omitted source
  pin becomes the same first-party `baseline` as `install`; a partially
  specified pin instead asks for `setup-ref`. Exact owner-local source setups
  use the held graph, including embedded components whose full reference
  matches the source member. They do not require public catalog publication.
  Omitted action is
  `add`. The engine records a new setup stable id, `fork_origin`, and
  `related_setup_ids` pointing at the source. The source identity remains
  held. Identical member sets do not mint. Compensated install remains
  `CliFailure` and the task `state` is `failed`. Missing context passports
  are minted in-process before plan, as for `install`. A catalogued harness
  config directory is not a project root. The model does not type
  `setup compose` or `setup update`.
- `REQ-8016`: Intent `author` drains `application.author`. It registers one
  directory as one embedded component and one setup identity. It asks
  directory, harness, kind, and name at most once each. Replay of the same
  bytes and native document path reuses the identity. A kind with no native
  surface for that harness is refused. Directory containers retain each source
  file's relative path
  under the named native component directory, including nested scripts;
  GENERATED.md source notes are excluded from the native projection.
  A single-file surface requires exactly one source file. Antigravity
  `instruction` and `command` each
  require exactly one `.md` source file and preserve its bytes at
  `config/rules/<name>.md` and `config/global_workflows/<name>.md`, respectively.
  They reject additional source files rather than dropping content or hiding
  it inside an unread nested directory. Their deterministic setup and embedded
  component identities bind the native path: reauthoring a legacy nested
  projection or choosing another native name mints new identities, leaving
  the old immutable versions unchanged. Other author identities retain their
  existing derivation. Names must be single native path segments. Unprojectable source trees return
  `AI_STP_VALIDATION_ERROR`, not an internal error. Author does not install
  and does not mutate a saved setup.
  Authoring retains validated embedded component bytes and immutable snapshots
  alongside the setup. Replaying older authored identities or installing a local
  definition restores missing embedded storage without reissuing any version;
  existing corrupt bytes remain a refusal.
- `REQ-8017`: Intent `switch` drains `application.switch`. It restores the
  newest user `preserved_setup` for the target, never an upstream catalog
  pin. Missing snapshot is refused without a catalog fallback. The
  project-root question names a project directory, not a harness config
  root. Drift is
  captured as a leftover, then the task blocks on `reload-session`.
  Compensated restore is `CliFailure` and the task `state` is `failed`. The
  CLI never kills the caller and never claims `session_loaded`.
- `REQ-8018`: Intent `account` drains `application.account`. Device-code
  login uses `actor=external`, one exchange per continue, and never
  `login.poll`. Login never uploads. Already signed-in login skips begin.
  An accepted current-account sync event binding an exact setup version permits
  local acquisition after sign-in, even when its immutable snapshot retains the
  original offline owner. Another account, a pending event, or a different version
  binding cannot supply that provenance. Provider validation still runs.
  Sync does not carry distribution artifacts: missing bytes still require exact
  catalog acquisition, including authenticated private publication access.
  An owned or accepted current-account exact private setup pin enables the
  acquisition service's authenticated fallback when its artifact is absent;
  another account or an unbound version does not enable that fallback.
  Sync push selects an existing syncable local entity by `stable_id`; a missing
  or unsupported identifier asks `stable-id`. Project roots are not account-sync
  entities, and local project passports remain on the device. A disabled-sync
  failure retains its exact configuration repair without enabling sync implicitly.
  Sync is explicit only; the selected action supplies the internal confirmation
  for both push and pull. Its typed `sync_result` preserves the underlying
  receipt, including conflicts and missing version coordinates. `synced` and
  the task goal are true only for an accepted push or an up-to-date pull.
  A nonempty pull page with a new cursor checkpoints its receipt in the same
  task at `planned` and emits a CLI continuation for the next page. Empty
  partial pages and repeated cursors settle without claiming the goal or
  polling unchanged data. Login does not call `/publications`, `/sync-plans`,
  `/revisions`, or catalog PUT.
- `REQ-8019`: Intent `publish` drains `application.publish`. A setup id routes
  through the existing setup publication set, including its exact component pins.
  The task checkpoints the planned `publication_set` before confirmation and emits
  a CLI continuation. Continue confirms that stored set digest; settled replay
  creates no new plans. The typed set receipt preserves member states, server
  evidence reasons and summaries, and transport error codes. Only
  `published` satisfies the readable goal. Component publication keeps the
  individual no-binding plan path. The task checkpoints that plan before
  confirming it. A `validating` or `publish_planned` receipt blocks on the
  external worker; continuing reads the same plan by ID without creating a
  second plan or confirming it again. Confirm retries use a stable key derived
  from the recorded plan ID; an already progressing plan is read, not posted
  again. Refused terminal states settle without
  claiming the goal. Visibility
  defaults to private. The plan omits `source_binding_id` and uses
  filesystem provenance. A bound git plan is refused. A worker receipt is
  not readable unless plan `state` is `published`. Missing auth blocks with
  one user code.
- `REQ-8020`: The twenty agent qualification corpus scenarios have a deterministic argv
  driver with no LLM. Concurrent `task continue` on one revision has one
  winner. A killed start after plan or apply records the child operation
  and a later continue resumes it. That INTERNAL envelope carries a `cli`
  continuation for `task continue` on the running revision. The driver covers change, author, publish
  private/public, login skip and idle-no-upload, relative project-root
  refusal, and auth-required publish. Missing native 7×3 and agent 20×5
  cells stay `not_run`; they are not success. An optional measured overlay
  (`AI_STP_QUALIFY_MEASURED`) may record `pass` or `fail` for executed cells;
  unknown keys and statuses are ignored so garbage cannot fill the matrix.
  New model evidence uses the `agent` overlay key; historical `haiku` keys
  are ignored and cannot be extended in place. The report preserves the
  overlay's `agy_model`; scored cells without a valid model identity report
  `null`, not the configured default. A scored
  overlay belongs to one model: scoring or filling it with a different or
  unknown recorded model is refused before workspace or driver effects and
  leaves the file unchanged. Native/isolation records and explicit
  invalidation preserve the attribution of retained cells. Same-model replay
  replaces the same cell without adding another entry; out-of-matrix run
  indexes are refused.
  Isolated `ai_stp_cli.agy_qualify` may run agent cells through `agy` with
  `gpt-oss-120b-medium` in a throwaway HOME; live results enter only through
  that overlay. Only this model is the current acceptance target; other model
  identities are diagnostics, never substitutes for its threshold. Isolated
  `agy` argv includes `--add-dir` of that throwaway
  workspace root and project so the model can exec from cwd without treating
  the host project path as out-of-sandbox. The isolated wrapper pins
  `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1` so a pending device-code cannot leak
  into the host keyring and fail a later cell as `AI_STP_AUTHORIZATION_EXPIRED`. Install exact-pin and without-pin
  prompts name the cwd-relative `--input` file and do not lead with the host
  absolute project path. Switch and a seeded change-add prompt do the same. The isolated wrapper refuses an argv token that is an
  absolute path outside that workspace root; a scored cell that logged such
  a path is `fail`. A logged `task answer` without `--value` is `fail`.   Overlay score for `install-exact-pin`, `install-without-pin`, `change-add-component`,
  and `switch-preserved-setup` is `pass` only when a completed registry row
  has `goal_satisfied` and `outcome.verified`. Overlay score for
  `author-directory` is `pass` only when a completed author row has `minted`
  with `setup_id` and `component_id`. Overlay score for
  `unsupported-project-local` is `pass` only when install stays blocked on
  `project-root` after `--value relative` and is not a verified install.
  Overlay score for `login-idle-no-upload` is `pass` only when account is
  blocked on `authorization` (or completed login with `login_uploaded` false)
  and a failed drain is `fail`. Overlay score for `publish-private`,
  `publish-public-filesystem`, and `auth-required-publish` is `pass` only when
  publish is blocked on `authorization`, or a completed row has filesystem
  provenance, empty `source_binding_id`, and the matching visibility; a failed
  drain is `fail`. Publish prompts name a cwd-relative `--input` and do not
  lead with the host absolute project path. Overlay score for
  `pending-reload-not-loaded` is `pass` only when switch is blocked on
  `reload-session` or completed with `outcome.verified` and
  `session_loaded` false; a failed drain is `fail`; model output must not
  claim the session loaded. That scenario seed-installs under
  `--docker-image` like `switch-preserved-setup`. Overlay score for
  `login-skipped` is `pass` only when `cli.log` has no ai-stp invocation and
  no upload markers. Overlay score for `expert-recovery-no-dump` is `pass`
  only when `cli.log` contains `task intents` and not `help --agent`. A verified `task start` that
  returns empty continuations is success (`REQ-8007`); a missing `task continue`
  is not a fail in that case. A `failed` drain, including isolation
  `AI_STP_DEPENDENCY_UNAVAILABLE`, is
  `fail`. Compensated-install, kill-after-apply, and concurrent-continue
  cells inject a real fault before the model turn instead of seeding an
  unmet install: the kill-after cell kills the consumer once its operation
  reaches `applied_unverified`, the compensated cell freezes the consumer
  process group while the provider's durable journal is mid-mutation and
  kills it only after target bytes diverge, and the concurrent cell races a
  second `task continue` and a `task cancel` against the live executor's
  drain. Injection evidence lands in `fault.json`; a cell whose fault could
  not be produced is `not_run`, and Docker cells record the same unrun
  marker because a container cannot drive the host's process groups. The
  overlay score reads the durable registry rows, never the model's claim:
  the fixture task must stay the only install task and hold exactly one
  operation, `completed` with `goal_satisfied` and a `verified` operation
  reconciles the effect, and a `failed` or `cancelled` task beside a
  `rolled_back`, `partial`, or `applied_unverified` operation is the honest
  recovery end. The compensated pass additionally requires `rolled_back`,
  a cleared provider journal, and target bytes restored to the recorded
  pre-mutation digests. A second install task or a second operation is
  `fail`. Opt-in   `--docker-image` (or `AI_STP_QUALIFY_DOCKER_IMAGE`)
  execs the isolated CLI inside privileged Docker so the provider local phase
  can be ENFORCED; the host product path stays unavailable when the host probe
  is denied. Explicit `--invalidate` drops scored agent overlay cells so fill
  can re-run them; `--invalidate-stale-verified` drops `install-exact-pin`,
  `install-without-pin`, `change-add-component`, and `switch-preserved-setup`.
  The
  runner prompt and score cover all twenty corpus names.
  Kill-after-apply resume and concurrent continue one-winner remain proven
  by the deterministic driver as engine properties; they are not exempt from
  agent cells. A capacity miss (`UNAVAILABLE` / 503) or an individual quota
  exhaustion (`RESOURCE_EXHAUSTED` / 429) with an empty `cli.log` does not
  record `fail`. An individual quota exhaustion pauses `--fill` so further
  cells remain `not_run` until capacity returns. A 503 after the model already
  invoked `ai-stp` is scored when the log shows follow-through or choreography;
  a start-only 503 retries a clean attempt and then stays `not_run`, not `fail`.
  A later capacity miss does not erase a previously scored `pass` or `fail`.
  `--fill` walks unrun cells one at a
  time with a 90s gap; a 503 empty-log cell stays unrun and the next attempt
  in the same walk may take a different unrun cell. Native-byte identity is
  an independent tree digest of provider-written files, not a stubbed
  envelope field. Its `ai-stp-qualify-tree/2` input contains an ordered JSON
  array of relative paths and content hashes, prefixed by the domain and a
  NUL byte. File content cannot impersonate another file boundary. Historical
  digests from the earlier unframed algorithm are not current evidence.
  Wheel and extra
  artifacts stay `not_built` until those bytes exist. `application/qualify.py`
  owns those cells, the promotion stages, and content hashes of the Skill,
  website prompt, and provider-kit identity. An overlay `isolation` key may
  record a host probe as `enforced` or `unavailable`; it never fills a native
  cell. A content hash is not a release claim.
- `REQ-8021`: One running mutating task per bound
  `(harness_id, project_root, scope)` when `harness_id` is known. Inspect may
  run concurrently. Unbound mutating tasks (no `harness_id` yet) do not refuse
  each other until a harness is bound; the later start, continue, or answer
  that would collide fails with `AI_STP_CONFLICT` naming the held `task_id`.
  Local registry schema 43 stores those columns and a partial unique index.
- `REQ-8022`: Invoking a command group that a shipped intent already drains
  (`install`, `auth`, `publication`, `sync`, `setup preserve`, `setup restore`,
  `setup preserved`, `setup compose`)
  without naming a declared leaf under that group is `AI_STP_VALIDATION_ERROR`
  with a `cli` continuation whose argv is
  `task start --intent <intent> --idempotency-key <intent>-session-01 --json`.
  An unknown top-level word that is a shipped intent name (`initialize`,
  `inspect`, `change`, `author`, `switch`, `account`, `publish`) is the same
  start continuation.
  An undeclared word under `task` (`task get`, `task info`, a missing leaf)
  and any other unknown command are the same error class with a `cli`
  continuation whose argv is `task intents --json`. Click usage text that
  lists `Commands:` is not an error message. An empty machine invocation
  (`--json` with no command) and `--help --json` are the same error class
  with that `task intents` continuation; they do not send `help --agent`.
  `task start --intent <shipped> --json` without `--idempotency-key` emits
  the start argv with `<intent>-session-01` rather than listing `task intents`.
  `task start --json` without `--intent`, `task start --intent` without a
  value, and `task start --intent` with a name that is not shipped list
  `task intents` and do not echo Click's missing-option or choice dump.
  A missing intent, including a positional intent after `task start`, names
  the required `--intent NAME` form in the refusal; it does not execute the
  guessed operation or accept a new positional form.
  `help --path` with no matching family lists `task intents` and does not
  send the full registry dump. An unscoped `help --agent --json` dump still
  carries a `cli` continuation whose argv is `task intents --json`. A scoped
  dump of a family a shipped intent already drains (`help --path install`,
  `auth`, `publication`, `sync`, `setup compose`, `setup preserve`,
  `setup restore`, `setup preserved`) carries that intent's start
  continuation.   A scoped dump of a mixed family (`component`, `select`,
  `setup`, `registry`, `config`) lists `task intents`. Other scoped dumps
  (`help --path doctor`) carry no continuation.
  A successful `task_pending` everyday leaf (`component discover --json`,
  `config init --json`)
  carries that draining intent's start continuation so a complete expert
  invocation still points at `task start`.
  A successful `task_covered` read (`install status --json`,
  `setup preserved list --json`) or plan (`install plan`,
  `publication plan`, `setup preserve plan`, `setup restore plan`)
  with empty handler continuations does the same. Handler continuations that
  name a qualify-forbidden leaf (`install apply` after `install plan`) are
  stripped first; if nothing allowed remains, the draining start is attached.
  `auth login` and
  `registry acquire` success do the same even though they are apply:
  login only records a pending device-code, acquire only materializes
  catalog bytes. Terminal apply/destructive success is not started again, so
  `install apply`, `auth complete`, and `setup compose apply` cannot loop;
  forbidden way-back on those envelopes is still stripped.
  `task answer --json` or `task continue --json` without `--task` emits the
  unique blocked human question's `task answer` argv when exactly one
  unsettled task exists; the same verbs with `--task` and without
  `--revision` emit that named task's answer argv. Many unsettled rows with
  no `--task` list `task list` so the caller picks by id; zero still list
  `task intents`. There is still no stored current-task pointer.
  The envelope does not
  list expert leaves and does not send `help --agent`. A declared
  `task_covered` leaf, or an everyday journey that is still `task_pending`
  (`setup compose plan`, `select propose`, `component adopt`,
  `component discover`, `component publish`), that fails
  Click parse or a bare handler `AI_STP_VALIDATION_ERROR` with no flags
  besides `--json` is the same start continuation as its draining group.
  `install plan --action backup` and
  `install plan --action rollback` stay expert recovery. A declared
  `auth login` that already has a supported `--provider` and fails for
  another flag keeps Click's subject. A declared expert leaf, or a
  `task_pending` leaf that is not an everyday journey (`sync preview`),
  stays unchanged.
  `AI_STP_AUTH_REQUIRED`, `AI_STP_AUTHORIZATION_EXPIRED`, and
  `AI_STP_AUTHORIZATION_PENDING` carry the
  account start as a `cli` continuation and do not name `auth login` or
  `auth complete`. A successful `auth login` with a provider does the same;
  `auth complete` success is not rewritten.
  An everyday leaf that already has extra flags and fails with expert
  `next_actions` (`install plan --proposal`, `select propose --harness`)
  or with an empty way-back keeps its error code and rewrites the
  envelope to the draining start. `install plan --action backup|rollback`
  stays a leaf error.
  Human `--help` for a group does not list qualify-forbidden leaves under
  `Commands:`; those leaves remain invokable and stay in `help --agent`.
  Nested drained leaves (`install transaction plan`, `publication
  visibility plan`, `component publish`, `setup import plan`, `select bundle`,
  `registry search`) are the same hide. A group whose remaining children are
  all hidden (`setup compose`, `component scaffold`, `setup import`) is
  itself omitted from the parent `Commands:` list. The `help` command is
  omitted from root `Commands:`. Qualify fails any logged `help` invocation,
  including unscoped `help --json` that dumps the registry without `--agent`.
- `REQ-8023`: Every schema urn the CLI emits — `result_schema` on a
  descriptor, `input_schema` on an intent, `details.schema` on a validation
  refusal — resolves at runtime. `schema list` is inspect-class and returns
  every exported schema id; `--find <text>` keeps only names containing it,
  and a miss is `AI_STP_NOT_FOUND`. `schema show --id` is inspect-class,
  accepts the bare name, the `urn:ai-stp:schema:v1:…` URN, or the generated
  `*.schema.json` file name, answers the JSON Schema document the
  `schemas/v1` gate publishes, and refuses an unknown id with the closest
  names in `details.candidates` and a `cli` continuation to `schema list`.
  A bare `schema` or an invented `schema` verb is `AI_STP_VALIDATION_ERROR`
  steering to `schema list`, not the task-intent catalog. `help --find <text>`
  keeps commands whose path or summary mentions the text, within the
  `--path` scope when both are given; a miss is `AI_STP_NOT_FOUND` with the
  `task intents` continuation, never an empty `commands` list.
- `REQ-8024`: `task list` is inspect-class and answers the durable tasks that
  have not settled — never settled history — each as id, revision, intent,
  state, the binding context (`harness_id`, `project_root`, `scope`), open
  question ids and `updated_at`, most recently touched first. It is the
  resume-discovery path for a caller that lost its reference or meets several
  open tasks, so a second start is never the only way to learn a task id. A
  missing registry answers an empty list rather than a failure; any other
  failure to open it is reported, not mistaken for empty.

## States and errors

Task `state` is distinct from envelope `ok`. `planned` is the mint row;
`task start` drains it before returning. A crash between mint and drain can
leave `planned`; replay of the same start key or `task continue` advances
it. `running` occupies a revision while effects execute.
`completed` means this intent finished; inspect stores
the doctor report and slim orientation in `outcome`. `cancelled` is a settled
abandonment. Unmet mutating goals on expert install paths remain `CliFailure`
per `REQ-1132`, including single-root apply and resume.

Unknown intent, missing task, and revision mismatch are registered failures
(`AI_STP_VALIDATION_ERROR`, `AI_STP_NOT_FOUND`, `AI_STP_CONFLICT`). Inspect
has no questions; `task answer` is refused.

## Security and privacy

Application services inherit the secret, path, and privilege rules of the
commands they serve. A service does not read a TTY prompt or a secret from
ordinary task JSON. Untrusted catalog or file text cannot become an executable
authority grant. `--input` is bounded and parsed as JSON, never executed.

## Compatibility and migration

Existing expert command paths remain. Registry descriptor `next_actions` may
narrow to scoped `help --path` orientation without removing a command. Envelope
`continuations` stay additive inside major 1. Continuation `argv` and `actor`
are additive on the continuation object. Local registry schema 42 adds
`agent_task`; the reverse drops that table. Schema 43 adds overlap columns
and a partial unique index on an open mutating binding.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-8001` | Import graph and unit tests: `ai_stp_cli.application` does not spawn a nested `ai-stp` process; provider `subprocess` is allowed; `capabilities` and `doctor` are served from that layer. |
| `REQ-8002` | `test_cli_capability_map` classifies every declared path into exactly one of five classes; unlabeled leftover fails; everyday install/compose/preserve/import/registry/adopt/discover/publication/login/init/select journeys are not `expert`; `component publish` is `task_pending`. |
| `REQ-8003` | The same test asserts the five lifecycle paths are `task_covered`; `task intents` is classified `inspect`. |
| `REQ-8004` | Expert handlers `capabilities` and `doctor` call application services rather than duplicating their bodies. |
| `REQ-8005` | Compensated and verified multi-root envelopes carry `operation_…` receipts; a started inspect task mints `task_…` in the payload, not as envelope `operation_id`. |
| `REQ-8006` | `test_cli_task` starts inspect to completion and compares `outcome.doctor` and `outcome.orientation` to `application.inspect` at the same moment; orientation has no `command_paths`; outcome `kind` is `inspect`. |
| `REQ-8007` | The same tests cover idempotent start, start draining a leftover `planned` row, start joining a leftover `running` row instead of returning empty continuations, concurrent start on one idempotency key joining instead of overlap conflict, replay of the original `--input` joining a drain-enriched blocked switch or account row, a contradictory `--input` on that key staying `AI_STP_CONFLICT`, revision conflict, concurrent continue one winner on a blocked revision, cancel, and status by id. Drain `CliFailure` carries `details.state=failed`. A catalog artifact stream timeout is `AI_STP_DEPENDENCY_UNAVAILABLE`, not `AI_STP_INTERNAL`. |
| `REQ-8008` | `application/task.py` does not import the command registry or resolve handlers by path. `test_cli_capability_map` asserts no `application/` module imports `ai_stp_cli.commands`. |
| `REQ-8009` | `test_cli_task` lists shipped intents from `task intents` and refuses an unknown name at start with a `cli` continuation whose argv is `task intents --json`, not `help --path task`; `test_cli_schema_discovery` asserts each descriptor's `input_fields` matches the validation model's fields and closed choice sets. |
| `REQ-8010` | Envelope unit tests cover JSON argument values, quoted display, dash-prefixed equals form, inspect start completing on the start argv, and a blocked human continuation that binds `question-id` and emits `task answer` argv without `value`. |
| `REQ-8011` | `test_cli_task` refuses inspect `--input` facts and round-trips `--input` through the parser; `test_cli_schema_discovery` parses a YAML object into the same facts, refuses duplicate keys and non-object documents, asserts a schema refusal carries `details.fields`, the `details.errors` pointer/issue/detail list, `details.schema`, and a `cli` continuation to `schema show`, and proves the declared stable-id and `X.Y` patterns refuse a malformed value at the boundary. |
| `REQ-8012` | Single-root apply tests for `failed`, `stale`, `partial`, and `rolled_back` raise the mapped `CliFailure` instead of returning `Answer`. |
| `REQ-8013` | `test_cli_initialize` asserts the section contract, catalog surfaces including custom `CODEX_HOME`, preserve-outside-markers, idempotent no-write, Cursor `alwaysApply` `.mdc`, HTML-comment refusal, antigravity limitation, that `application/initialize.py` contains no file-write verbs, that omitted drain kwargs with no bind stay `provider-too-old`, that a remembered chosen provider without the op or without `instruction_section` stays too-old, that a discovered row is not a bind, that declaring both invokes the provider path, that `--instruction-section` is on plan argv only then, and that a drain `CliFailure` keeps `details.task` and drops expert `next_actions` such as `provider network`. Fake-provider tests still replace `provider_operations` / `patch_via_provider`. `test_cli_plan_request_fields` accepts `instruction_section` on `plan_request_fields` and sends `--instruction-section` only for `patch_instruction_region` when that field is declared. `test_cli_task_driver` continues a `provider-too-old` block without writing. Skill and qualify treat `provider-too-old` as not login. |
| `REQ-8014` | `test_cli_install_task` asks harness/setup-ref/project-root once, drains plan→approve→apply in one start, maps compensated and partial apply to `CliFailure` with task `failed`, resumes a held child after a killed start, refuses a relative project root, re-asks when `project_root` is a catalogued harness config directory, mints missing developer/device/project passports before plan, passes the catalogued harness config root as `target`, and strips expert `next_actions` such as `provider network` from drain failures. |
| `REQ-8015` | `test_cli_change` mints a new setup id with `fork_origin` and `related_setup_ids`, keeps the source id held, skips minting on a no-op member set, drains derive→install in one continue, maps compensated apply to `CliFailure`, mints missing context passports before plan, and adds a locally authored embedded component without catalog acquire. |
| `REQ-8016` | `test_cli_author` registers a directory as one component plus one setup identity, asks typed questions once, reuses the identity on replay of the same bytes, verifies exact Antigravity skill archive paths and bytes for single-file and nested-script trees, omits generated notes, refuses invalid names and multiple files on a single-file surface, verifies immediate named Antigravity Markdown projections and unchanged payloads, replays the same native name, forks changed names and legacy nested identities without overwriting either version, reports unprojectable trees as validation errors, refuses a kind with no native surface, and contains no nested CLI process. |
| `REQ-8017` | `test_cli_switch` restores the newest user `preserved_setup`, refuses a missing snapshot without a catalog fallback, asks for an absolute project directory rather than a harness config root, re-asks when `project_root` is inside a catalogued harness config directory, captures drift then asks `reload-session`, replays the original `--input` onto that blocked row without a second restore, maps compensated restore to task `failed`, and never kills the caller or claims `session_loaded`. |
| `REQ-8018` | `test_cli_account` drains device-code login with `actor=external`, one exchange per continue, no `/publications` `/sync-plans` `/revisions` or catalog PUT on login, skipped begin when already signed in, explicit sync only, and never `login.poll`. |
| `REQ-8019` | `test_cli_publish` defaults visibility to private, omits `source_binding_id`, checkpoints the component plan before confirm, holds `validating` as an external wait, resumes through status on that same plan, treats only `published` as readable, blocks missing auth with one user code, and refuses a bound git plan. |
| `REQ-8020` | `test_cli_task_driver` and `test_cli_install_task` drive the twenty corpus scenarios without an LLM: relative project-root refusal, change add, author directory, publish private/public filesystem, login skip and idle-no-upload, auth-required publish, partial/compensated install with recover not re-apply, kill-after-plan and kill-after-apply resume (INTERNAL envelope carries `task continue` argv), concurrent continue one winner, antigravity limitation, custom-home section through provider hooks, pending-reload not loaded, skill under 500 lines without a 203-command dump, install exact pin with an independent native-bytes tree digest. `test_cli_qualify` proves measured model attribution and unambiguous file-tree digest framing; `test_cli_agy_qualify` refuses mixed/unknown-model scoring before effects, preserves model attribution through native probes and invalidation, and rejects out-of-matrix run indexes. `application/qualify.py` owns native 7×3, agent 20×5, promotion stages, and wheel/extra claims; cells that were not executed stay `not_run` and are not success; a measured overlay may record only `pass` or `fail` for known cells; isolated `agy_qualify` prompt and score cover all twenty corpus names and write overlay only; a capacity miss with an empty `cli.log` does not record `fail`; a 503 after follow-through or choreography is scored; a start-only 503 retries a clean attempt and stays `not_run` after those retries; a later capacity miss does not erase a previously scored `pass` or `fail`; `--fill` skips a 503 empty-log cell to the next unrun cell in the same walk; isolated `agy` argv `--add-dir`s the throwaway workspace root and project; install exact-pin, without-pin, switch, and seeded change-add prompts do not lead with the host absolute project path; the isolated wrapper pins `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1` so a pending device-code cannot leak into the host keyring; the isolated wrapper refuses an argv path outside the throwaway workspace and score fails a logged escaped path; a logged `task answer` without `--value` is `fail`; overlay score for `install-exact-pin`, `install-without-pin`, `change-add-component`, and `switch-preserved-setup` is `pass` only when a completed registry row has `goal_satisfied` and `outcome.verified`; overlay score for `custom-home-section` is `pass` only when a completed initialize row has `wrote` for codex and `CODEX_HOME/AGENTS.md` contains the marked section (that catalogued path is not invented); overlay score for `fresh-initialize-prompt` is `pass` only when a completed initialize row has `wrote` with marked catalogued instruction bytes or limitation `no_global_instruction`; overlay score for `antigravity-limitation` is `pass` only when that limitation is recorded, `wrote` is false, and `harness_id` is antigravity; overlay score for `author-directory` is `pass` only when a completed author row has `minted` with `setup_id` and `component_id`; overlay score for `unsupported-project-local` is `pass` only when install stays blocked on `project-root` after `--value relative` and is not a verified install; overlay score for `login-idle-no-upload` is `pass` only when account is blocked on `authorization` (or completed login with `login_uploaded` false) and a failed drain is `fail`; overlay score for `publish-private`, `publish-public-filesystem`, and `auth-required-publish` is `pass` only when publish is blocked on `authorization`, or a completed row has filesystem provenance, empty `source_binding_id`, and the matching visibility, and a failed drain is `fail`; publish prompts name a cwd-relative `--input` and do not lead with the host absolute project path; a verified start with empty continuations is success; a `failed` drain, including isolation `AI_STP_DEPENDENCY_UNAVAILABLE`, is `fail`; fault cells inject a real fault before the model turn (kill at `applied_unverified`, provider kill mid-mutation with a surviving journal, a continue/cancel race against the live executor), record the evidence in `fault.json`, and score only the durable registry rows: one install task holding one operation, `completed`+`verified` or the honest `failed`/`cancelled` recovery end, and for `compensated-install` additionally `rolled_back` with a cleared journal and restored target digests; a cell without a produced fault stays `not_run`; a second install task or second operation is `fail`; opt-in `--docker-image` execs the isolated CLI inside privileged Docker so bwrap can ENFORCE without adding a Linux unisolated product path; explicit `--invalidate` / `--invalidate-stale-verified` drop scored agent cells so fill can re-run initialize/install/change/switch/custom-home under the verified scorer; overlay `isolation` records a host probe and never fills a native cell; wheel/extra stay `not_built`. Artifact identities are content hashes, not a release claim. Dirty trees are refused as release candidates. |
| `REQ-8021` | `test_cli_task` allows two inspect tasks together, refuses a second mutating start on the same harness and scope, allows different project roots, and refuses answering the same harness onto a second open mutating task. |
| `REQ-8022` | `test_cli_app` redirects `install --json`, `install --harness`, a stray path under `install`, `auth --json`, `sync --json`, `publication --json`, `setup preserve --json`, `setup restore --json`, `setup preserved --json`, `setup compose --json`, and unknown top-level shipped intent names (`initialize`, `inspect`, `change`, `author`, `switch`, `account`, `publish`) to `task start` for the matching intent with a `cli` continuation; `task get --json`, `task info --json`, `nope --json`, empty `--json`, and `--help --json` list `task intents` and do not send `help --agent`; Click usage dumps for incomplete groups (`component --json`, `registry --json`, `select --json`, `setup --json`, `config --json`) list `task intents` and do not name expert leaves; `task start --intent initialize --json` without the key emits `task start --intent initialize --idempotency-key initialize-session-01 --json`; `task start --json` without `--intent` and `task start --intent` with an unshipped name list `task intents` and do not echo Click's missing-option or choice dump; `task answer --json` and `task continue --json` without `--task` resume the unique blocked human question, list `task list` when many unsettled rows exist and `task intents` when zero; those verbs with `--task` and without `--revision` resume the named task even when other rows are open; `help --path` with no matching family lists `task intents` and does not send `help --agent`; an unscoped `help --agent --json` dump carries a `task intents` continuation; a scoped `help --path install --json` carries the install start continuation; scoped mixed families (`component`, `select`, `setup`, `registry`, `config`) list `task intents`; `help --path doctor` carries none; a `task_covered` leaf without required input (`install plan --json`, `auth login --json`, `publication plan --json`, `setup compose apply --json`) emits the draining `task start` line; everyday pending leaves (`setup compose plan --json`, `select propose --json`, `component adopt --json`, `component discover --bogus --json`, `setup import inspect --json`, `component publish --json`, `registry search --json`, `publication status --json`, `setup preserved show --json`) do the same; a successful `component discover --json` carries the author start continuation; a successful `config init --json` carries the initialize start continuation; `install plan --action backup --json` and `sync preview --json` do not; `test_cli_cloud` `AI_STP_AUTH_REQUIRED` / `AI_STP_AUTHORIZATION_EXPIRED` / `AI_STP_AUTHORIZATION_PENDING` carry the account start continuation and do not name `auth login` or `auth complete`; `test_cli_capability_map` `everyday_success_start_intent` covers `auth login` apply success and not `auth complete`; extra-flag everyday leaf failures (`install plan --setup`, `select confirm --proposal`) do not name those expert leaves; a successful `install status --json` and `setup preserved list --json` carry the draining start; `test_cli_capability_map` `everyday_success_start_intent` covers covered `plan` success (`install plan`, `publication plan`, `setup preserve plan`), `auth login` / `registry acquire` apply success, and not `install apply`; `test_cli_app` `_everyday_success_envelope` strips `install apply` from plan success then starts install, and terminal apply keeps `install recover` while dropping `install plan`; `test_user_docs_everyday_first_copy` forbids qualify-forbidden leaves in every user-facing bash fence and in table cells that wrap an `ai-stp` argv in backticks; `test_cli_process` `install --help` / `auth --help` / `select --help` omit forbidden `Commands:` leaves while `install plan --help` remains; `install transaction --help` omits plan/approve/apply; `setup --help` omits compose/scaffold/update/restore/import; `component --help` omits scaffold/publish; `publication visibility --help` omits plan/confirm; `select --help` omits bundle/graph; `registry --help` omits search/acquire; `ai-stp --help` omits `help`; `test_cli_agy_qualify` `choreographed` fails unscoped `help --json`. |
| `REQ-8023` | `test_cli_schema_discovery` resolves `schema show --id` for a bare name, the full URN, and the generated file name to the same document as the model's JSON Schema; `schema list` names every exported id and `--find` filters names; an unknown id is `AI_STP_NOT_FOUND` with `details.candidates` and a `schema list` continuation; every `input_schema` the intents catalog emits resolves to its model; both paths classify `inspect`; `help --find` filters path and summary within `--path` scope and a miss is `AI_STP_NOT_FOUND` with the `task intents` continuation. |
| `REQ-8024` | `test_cli_task` lists only unsettled tasks newest-first with binding context and open question ids, answers an empty list on a fresh registry, and propagates an open failure that is not `AI_STP_NOT_FOUND` rather than answering empty; `test_cli_app` proves two open rows steer bare `task answer`/`task continue` to the `task list` argv while a named task still resumes its own answer argv. |
