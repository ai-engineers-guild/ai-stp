---
description: "Mandatory checks by component type, MCP class, and setup."
last_verified: "2026-09-02"
---

# Validation policy

The requirements owner is `SPEC-007`. This document defines the machine
boundary: which checks are mandatory for each object type, what their results
mean, and when an object is eligible for publication and for the
`authoritative` trust line.

Each check returns a state from `SPEC-007` and stores the evidence source, tool
version, policy version, and time. Tool unavailability produces `not_run` or
`degraded` and never becomes `passed`.

The public result projection contains a bounded, sanitized `reason` for an
unsuccessful or incomplete check. Raw scanner messages, secrets, and local paths
are not sent to the catalog.

## Operational evidence for safety-scan

For `platform_safety_scan`, the worker stores only bounded in-process telemetry;
it is not a replacement for `SafetyScanRun` and contains no payload, idempotency
key, full paths, or raw tool output. Mandatory signal groups are:

- queue: claim/empty-poll/claimed/requeue counters, queue wait buckets, and
  handler duration/result;
- suite: total/cache-hit, sum/avg/max, and fixed p50/p95/p99 duration buckets;
- check: total/result by `check_id`, sum/avg/max duration, and fixed duration
  buckets;
- external execution: timeout/missing counters and sandbox mode counts.

Fixed buckets bound cardinality; `+Inf` means the upper bucket boundary was
exceeded, while a `null` quantile means that the corresponding rank fell into
`+Inf`. A process-local snapshot is acceptable for diagnostics, but production
readiness MUST have reproducible offline evidence through
`just safety-benchmark`: the benchmark forcibly disables external CLI and the
network, uses a fixed corpus/order, and separately marks machine-dependent
wall-clock measurements.

Evidence on the adversarial corpus belongs to the versioned manifest in
`tests/fixtures/safety-corpus/`: every component type and setup has 10 to 20
relevant malicious examples and at least two clean control examples. The
sequential server run fails on a missing expected `check_id`/`rule_id` or any
finding in a clean control example; external CLI and the network are disabled
for this evidence.

## Result classes

| Class | Meaning |
|---|---|
| blocking | Failure prohibits publication and excludes the version from the `authoritative` line. |
| warning | Failure does not block, but is visible in the card, search, and report. |
| not_applicable | The check is not meaningful for this type; absence of a result is valid. |
| not_run | The check is mandatory but was not run; the version is not considered verified. |
| expired | Evidence was obtained but has exceeded the policy lifetime. |

An unknown component type and an unknown transport class fail closed. Skipping
an unknown value is prohibited.

## Common checks

The following are mandatory for every published version:

- passport schema and canonical serialization;
- exact public repository, commit, and subpath, or the local artifact hash for
  a private version;
- artifact hash, size, and file list;
- license and redistribution rights;
- bounded safe paths and regular files only;
- secret scanning;
- exact dependencies and required capabilities;
- compatibility with the harness, its version, system, and architecture;
- non-empty normalized tags;
- author and version state on both verification axes;
- tool and policy versions and evidence lifetime;
- independent server-side hash recomputation and non-executing structural
  validation for a public version.

## Server safety-scan (platform_safety_scan)

During `validate`, after passport checks, worker/platform executes the staged
safety suite (`policy_version` of the form `safety-2`, registry in
`ai_stp_platform.safety.policy`).

| Family | check_id (primary) | Source | Mandatory (public component) |
|---|---|---|---|
| unpack | `artifact_unpack` | workdir + digest re-verify | yes |
| path | `path_denylist` | in-proc | yes |
| secrets | `secrets_heuristic` (+ optional `secrets_gitleaks`) | in-proc / CLI | heuristic yes; gitleaks findings outside `tests/` force-block; fixture hits under `tests/` stay warning-class |
| prompt_injection / stego | `pi_content_pack`, `content_hidden` | in-proc | warning-class by default |
| network intent | `network_intent` | offline in-proc, without DNS/reputation lookup | warning-class by default |
| agentic behavior | `agentic_behavior` | bounded offline in-proc patterns | yes |
| sast | `sast_opengrep` (+ shellcheck/bandit by language) | owned rules / CLI | policy |
| mcp | `mcp_config_static` | in-proc | yes when MCP present |
| hook | `hook_schema_static`, `hook_command_argv` | in-proc | yes when hooks present |
| skill | `skill_static_gate` (Cisco static + behavioral data-flow + independent platform rules) | CLI + owned | yes for skill/agent |
| obfuscation | `shell_obfuscation` | bounded in-proc decoding, no more than two layers | warning-class by default |
| sca | `sca_osv` | CLI offline preferred | warning-class |
| malware | `malware_clamav`, `malware_yara` | local marker + clam/yara | strict profile |
| sca lang | `sca_pip_audit`, `sca_govulncheck`, `sca_cargo_audit`, `sca_cargo_deny`, `sca_npm_audit` | CLI when manifests/lang | policy |
| sast lang | `sast_gosec`, `sast_eslint_security` | CLI when lang present | policy |
| document | `document_pdf` | PDF JS/OpenAction/PI strings | policy when pdf |
| setup | `setup_pin_aggregate` | catalog pin `checks_summary` join, no tree re-scan | yes for setup |

Gitleaks still force-blocks a secret in the component payload. Hits under `tests/`
or `test/` stay in the record as warning-class so a committed skill tree can
include scanner fixtures without dropping those files from the snapshot.

`agentic_behavior` covers only mechanically provable declarations: recursive
delegation, trust in a subagent's result, permission substitution, reading
adjacent agents, self-modification, persistence, permission masking, argument
substitution, scope expansion, passing results to the shell, unsafe
deserialization, floating dependencies, memory poisoning, remote instructions,
and escaping the root. Matches are line-scoped. Defensive or detector wording
(`never`, `avoid`, `detect`, `unpinned`) and Semgrep/Opengrep `pattern:` lines
are not declarations. Unpinned `npx`/`uvx` is checked on agent instruction
files (`SKILL.md`, `AGENT.md`, and the same family), not on README, scanner
source, or a pinned `@`/`==` token. It does not attempt to semantically assess
whether a component acts in good faith. `mcp_config_static` separately parses
tool/schema/resource/prompt/output metadata, name collisions and shadowing,
dangerous capability chains, and changes to the canonical tool definition
between approved and current snapshots. For Codex, Grok Build, and OpenCode
configuration contributions it also rejects package archives, whole host files,
and arbitrary TOML/JSON: the artifact must be one parseable map from non-empty
server names to command or URL definitions that can be inserted under the
harness-owned MCP key.

Public audit: `GET /v1/catalog/{components|setups}/{id}/versions/{version}/checks`.

Each unsuccessful audit row may carry `finding_summary`: a bounded count,
maximum severity, sorted canonical `rule_ids`, safe relative `paths`, and
`truncated`. This is a projection of identifiers, not findings: payload, source
lines, stdout/stderr, absolute paths, secret values, and arbitrary scanner
messages are excluded. An unsafe rule ID is replaced by the tool identifier; an
unsafe path is not published.

Result rules: `not_run` / `degraded` for mandatory checks do **not** become
`passed`. External CLIs are enabled only when `AI_STP_SAFETY_EXTERNAL_CLI=1`.

The regex keyword set owned by `skill_static_gate` is a fallback path, not a
second opinion. When `skill-scanner` loaded the skill package and reached a
verdict, findings from this set are recorded as `medium` and do not fail by
themselves; when the engine is absent or did not finish reading—including
timeout and launch failure—the set retains its original severity and fails. The
reason lies at the method boundary: a keyword scan cannot distinguish a skill
that exfiltrates credentials from a skill that searches other code for such
exfiltration, and declaring the latter `critical` on top of a clean engine read
would make the fallback override what it replaces.
Card percentage: `passed / (passed+failed+warning)`; statuses `not_applicable`
and `skipped` are excluded from the denominator. Status is `pending` when any
applicable mandatory check is `not_run`, `degraded`, or `running`.

## Checks by component type

| Type | Mandatory checks in addition to common checks |
|---|---|
| `instruction` | native format and frontmatter; size and inclusion limits; precedence and conflict analysis; undeclared remote instruction sources prohibited |
| `skill` | `SKILL.md` form and metadata; list of resources, attachments, and scenarios; declared tools and permissions; static checks and scenario type checks; bounded smoke run where applicable |
| `mcp` | depends on the transport class; see below |
| `hook` | event and matcher schema; execution only as an argument array without unsafe substitution; time, exit-code, and blocking semantics; static scenario checks; event fixtures |
| `command` | metadata and arguments; effect class; validation of referenced scenarios and files; permissions and confirmation class; invocation fixture |
| `agent` | role, model, tools, and delegation declaration; native schema; hidden remote prompts prohibited; conflict and permission resolution |
| `plugin` | native manifest; list of nested components; exact dependency graph; smoke installation and loading by the provider; native identifier conflicts |
| `setting` | typed key and value schema; merge, precedence, and conflict policy; secrets prohibited in the value; native validation by the target |

## MCP transport classes

| Class | Mandatory checks |
|---|---|
| `local_exec` | exact source and integrity; package installation scripts disabled by default; declared arguments, environment-variable names, secret requirements, and transport; dependency, static, and secret checks; protocol handshake and smoke validation of tool, resource, and prompt schemas in an isolated temporary home directory without real credentials |
| `package` | same as `local_exec`, plus an exact package version, lock file, and package-source integrity evidence |
| `remote_https` | canonical HTTPS address and authentication classification; endpoint-ownership evidence where available; schema snapshot; bounded platform-side validation; server-side request forgery protection, including private, local, and link-local addresses and repeated name resolution; evidence lifetime; prohibited from claiming security of unavailable implementation source code |

The transport class is declared in the passport and checked before policy
selection. A remote endpoint does not inherit assumptions of a local package.

If an object declares a need for credentials, handshake and smoke validation are
performed without them wherever possible: the platform does not request or store
someone else's keys. A mandatory check executable only with real credentials is
run locally by the author with their own credentials through the ordinary
bounded tool path, and the CLI issues a signed author attestation under
`ADR-0026`. Until that attestation exists, the check remains `not_run` with
reason `missing_required_credentials`, and public publication is blocked: a
mandatory check without accepted evidence is not skipped.

## Setup checks

In addition to common checks, a setup MUST pass:

- exact component version references;
- graph construction and cycle resolution;
- resolution of conflicts, licenses, access, and permissions;
- mapping of execution profile `full-auto` to native provider capabilities;
- deterministic composition and composition/transformation reports;
- deterministic `HarnessBundle`;
- provider `validate-bundle` and `plan-bundle` without changing the target;
- smoke installation for claimed compatibility;
- launch evidence only for support levels that claim it.

## Eligibility for publication and a trust line

Publication requires every mandatory check to have current, policy-accepted
evidence with result `passed`. A mandatory check in state `failed`, `degraded`,
`not_run`, or `expired` blocks public publication. A completed `warning`-class
check does not block publication.

The accepted evidence source is defined for each check:

| Check class | Accepted evidence |
|---|---|
| executable without credentials | server execution: `platform_digest_verified`, `platform_structure_verified`, and re-execution of the check by the platform |
| requires credentials or external author authorization | signed author attestation of the exact hash: `author_attested` under `ADR-0026` |
| installation evidence | `provider_installation_tested` |
| launch evidence | `runtime_tested` |

A device report does not replace a check the platform can execute itself. On
publication, the server always independently recomputes the hash and structure,
reruns all credential-free mandatory checks, validates the signature, binding,
freshness, and versions of the author attestation and the device and account
states, and evaluates policy.

`component_verified` means that all mandatory checks for the version have
current accepted `passed` evidence. The flag describes evidence completeness and
policy acceptance, not that the platform executed every check: the card and
machine output show each check's evidence source and its limitations. The flag
is not permanent: it is removed when evidence becomes `expired` or when a
stricter policy version adds a mandatory check the version lacks. Therefore,
published versions and verified versions are distinct sets, and the latter
changes over time without changing bytes.

The flag does not follow from authorship and is not granted manually. A version
with `warning` is published but does not become verified.

## Installation eligibility

Eligibility of a version for new installations is derived from the freshness of
mandatory evidence under `ADR-0032`. As soon as any mandatory evidence ceases to
be a current `passed`—because it expires, fails revalidation, or policy is
tightened—the version simultaneously:

- loses `component_verified`;
- leaves the `authoritative` line;
- is blocked for new installations and updates without a separate manual step.

An already installed target continues to operate and receives a prominent
warning with the reason; remote disabling and target removal are not performed.
Manual state `blocked` under `SPEC-005` remains a separate moderator action on
top of this rule.

The author restores eligibility with a new passing `ValidationSnapshot` for the
same immutable bytes. Changed bytes require a new version. An offline client uses
the last known eligibility state with its check time and applies the current
state on the first update.

The `authoritative` line under `ADR-0016` additionally requires
`author_verified`, `component_verified`, and no `expired` mandatory evidence.
The `experimental` and `local_owner_or_pinned` lines do not relax safety
prohibitions: they change inclusion conditions, not the set of mandatory checks
for installation.

## Author attestation

An author attestation is a device-key-signed record of local execution of a
credential-dependent check. It is bound to:

- the exact object hash and component or setup version;
- the validation-policy version and tool versions;
- the harness and provider versions against which validation ran;
- identifiers of the executed test cases and the result;
- the author account, device, and execution time.

Secret values, tokens, credentials, credential-issuance addresses, and sensitive
diagnostics are not included in the attestation and are not serialized. The
record hash is computed in the `ai-stp:attestation:v1` domain according to
`canonical-data.md`.

The CLI creates such a record with `attestation sign` only for an exact locally
released version and saves it as a new owner-only JSON file without overwriting.
Signing requires an active cloud session and a local key from one device, plus
explicit confirmation before writing. `publication plan` accepts files through
repeatable `--attestation-file` and, before a network call, checks the closed
model, signature, absence of duplicates, and equality of all coordinates with
the version being published. The `/v1` wire request carries the same closed
record, not a reduced projection: the server owns the single payload definition,
Ed25519 verification, and coordinate checks under `ADR-0092`. The shape of a
signature string is not evidence by itself.

An attestation is invalid if the object hash, policy version, tool versions, or
test-case set changes, and also after device revocation. An invalid attestation
returns the check to `not_run` and closes publication until a new one exists.

## Versioning

The matrix is versioned with the schema. Policy tightening does not rewrite
historical snapshots; its effect on old versions is defined by the installation
eligibility section: missing mandatory evidence blocks new installations and
updates without affecting installed targets.
