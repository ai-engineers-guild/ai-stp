---
description: "SPEC-011: CLI, machine help and agent skill."
last_verified: "2026-08-29"
---

# SPEC-011: CLI, machine help, and agent skill

## Purpose

The user installs the CLI with a command from the site via `uv`, and the agent securely manages passports, indexing, compilation, validation, and installation through a stable machine contract and a canonical skill.

## Scope

Includes installation and initial setup, strict JSON, feature and schema help, plan and application separation, daily work cycle, one global user config, seven skill projections, a secure control layer and a privilege escalation boundary. The graphical orchestrator, hidden shell commands, native model invocation, and password passing to the agent are not included.

## Terms

- `machine help` - versionable description of commands, fields, change class and next actions.
- `control-plane Skill` - secure integration of `ai_stp`, separate from the user setup being replaced.
- `full-auto` - the profile of the agent’s work with the code, and not the unconditional permission of external actions; one of three independent axes according to `ADR-0017`.
- `global config` is the only custom CLI settings file that does not contain secrets.

## Requirements

- `REQ-1101`: The CLI is installed by a published command via `uv` in the user environment without the required `sudo`.
- `REQ-1102`: Machine output uses one strong versioned JSON object on standard output and robust completion and error classes; machine help publishes a separate `handling` for each error code, because the common exit class does not define the agent action.
- `REQ-1103`: A sensitive change has an immutable plan and a separate apply step using an exact hash.
- `REQ-1104`: Automatic code work does not remove confirmation from publication, release a major version, install an unverified object, escalate privileges, perform full cleanup, delete a target or backup, perform an external Git action, or deploy.
- `REQ-1105`: One canonical agent skill creates testable native projections for seven harnesses.
- `REQ-1106`: The skill obtains commands, schemas, and error handling from machine help, rather than copying parameters, exit codes, or error disposition manually.
- `REQ-1107`: The control skill is not deleted or overwritten by a custom setup.
- `REQ-1108`: The password, token, and privilege escalation secret are never passed to the agent, CLI arguments, standard input, environment, or log.
- `REQ-1109`: Unknown harness and native configurations found in it are recorded as unknown observations; setup, option, target and adaptation draft are not created for them, and an attempt to apply it returns error `AI_STP_UNSUPPORTED_APPLY` with a list of supported harnesses.
- `REQ-1110`: The actions of read, draft, add, delete, update and install a component are declared in the machine help and always go through the setup version, package and provider plan.
- `REQ-1111`: A detected native configuration without a registered setup is first formalized into a personal setup in a separate explicit step.
- `REQ-1112`: Daily work is expressed by the actions `status`, `rescan`, `search`, `diff`, `update` and `rollback`; There is no automatic update, release channels, or background daemon.
- `REQ-1113`: `status` shows the project, setup, harness, selected and installed versions, pending installation status, both types of discrepancies and the result of checking the required environment variables by name.
- `REQ-1119`: The discrepancy distinguishes between `local_drift` - the target was changed outside the provider's lifecycle and does not correspond to the passport of the installed version - and `catalog_drift` - a newer version is available for the assigned object; waiting for the selected version to be installed is not a discrepancy and is shown by the `pending_install` state, and each state names its own safe next action.
- `REQ-1120`: Neither type of discrepancy is resolved automatically: `local_drift` suggests restoring or filing changes into a new version, `catalog_drift` suggests updating after the plan.
- `REQ-1114`: One global user config specifies the availability and address of the public directory, enabling cloud synchronization, local registry path, local search parameters, explicit project discovery roots, and enabling and address of anonymous telemetry ping; the private list of fields and default values ​​belong to `docs/contracts/cli-config.md`.
- `REQ-1115`: The config does not contain secrets, does not replace passports, and an unknown key returns a clear typed error.
- `REQ-1116`: The CLI shows the effective configuration without secrets, and precedence is default, then global config, then an explicit command argument.
- `REQ-1117`: Offline mode is achieved by disabling directory and synchronization in the config and does not require other changes.
- `REQ-1118`: The CLI and each of its commands do not call model interfaces, do not require a model credential and do not depend on the optional server presentation enrichment `SPEC-053`.
- `REQ-1121`: Recommendation session, suggestion display and confirmation are declared in machine help; creation of `SetupVersion` from a proposal is only available through the confirmation action of `docs/contracts/selection-proposal.md`.
- `REQ-1122`: The complaint command is declared in the machine help, collects only the mechanical fields of the allowed list `docs/contracts/report-case.md`, shows a full preview and submits the case only after the user's explicit consent.
- `REQ-1124`: Diagnostics reports the preconditions for creating a setup with a separate check, the state of which remains `ready` in their absence, and `detail` names the exact commands for creating missing passports. The list of these commands has one owner and matches the list named by the corresponding command's refusal.
- `REQ-1123`: For integration scenarios, machine help allows you to build argv without parsing prose: mandatory, type, repeatability and private parameter values ​​are structured, and each payload is associated with a published schema; the update is expressed by an exact version selection and `install plan` with `action=update`, rather than a hidden automatic command.

## States and errors

The primary setting has the states `ready`, `needs_user_action`, `partial` and `failed`. `ready` means that the installation is working, and not that everything that the assembly can do is available: the preconditions of individual commands do not control the state and are reported in the `detail` of the corresponding check. Machine JSON always distinguishes between retryable and permanent errors. A crash before the envelope is built can use the error stream, but does not print secrets. An unsupported command or schema returns a typed update hint.

## Security and privacy

The CLI uses the system's secure storage for cloud credentials and user directories for the toolset. The contents of the repository and the output of the tool are considered untrusted. The agent does not validate its own external record. Privilege escalation is only done through human system interaction or returns `needs_user_action`.

## Compatibility and migration

Machine JSON, help and skill projection have versions. Unknown optional fields are ignored; the unknown major version of the schema is rejected. The version of the projection generator and the hash of the canonical skill are recorded, and the semantic loss blocks the trusted projection.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1101` | A clean install on Linux x86_64 runs the published command without administrator rights; an unverified macOS line is not called supported. |
| `REQ-1102` | Benchmark checks for JSON, completion codes and the full error registry check standard flows, different handling for conflict/user-decision of the same class and unknown fields. |
| `REQ-1103` | A changed or outdated plan will block application. |
| `REQ-1104` | Interaction policy checks require a user decision for each sensitive class. |
| `REQ-1105` | Reference projections cover Claude Code, Codex, Pi, OpenCode, Grok Build, Cursor and Antigravity. |
| `REQ-1106` | The contract skill check receives parameters and error handling only from `help --agent --json` and does not contain a manual exit classes table. |
| `REQ-1107` | End-to-end check of setup switching preserves control skill. |
| `REQ-1108` | Checks of processes and logs confirm the absence of passwords and secrets. |
| `REQ-1109` | The unknown harness fixture does not create any managed objects and returns a typed error with a list of supported ones. |
| `REQ-1110` | Contract verification proves that adding a component creates a new version of the setup and does not write directly to the target. |
| `REQ-1111` | End-to-end testing on targets without a setup requires an explicit design step before application. |
| `REQ-1112` | The machine help announces exactly these six actions, and a code search does not find the automatic update scheduler. |
| `REQ-1113` | The reference response `status` contains all the fields listed and does not contain variable values. |
| `REQ-1114` | The config fixture covers every field and default value. |
| `REQ-1115` | The unknown key and secret-like value are rejected and the location of the error is indicated. |
| `REQ-1116` | The priority check proves the order and absence of secrets in the output of the running configuration. |
| `REQ-1117` | Disabling directory and synchronization goes through a stand-alone end-to-end path. |
| `REQ-1118` | Checking the dependency closure and running the CLI rejects the model client, model credential, and dependency on the enrichment endpoint. |
| `REQ-1119` | The fixture of the target changed outside the provider gives `local_drift`; another stable ID with the same `X.Y` gives `pending_install`; `catalog_drift` appears only for the numerically larger canonical version (`1.10 > 1.9`), does not appear for the older directory and does not mix with local drift. |
| `REQ-1120` | No divergence fixture changes the target without the individual decision of the user. |
| `REQ-1121` | Contract checking does not find a way to create a version from a proposal past the confirmation action. |
| `REQ-1122` | The complaint record shows a preview, rejects submissions without consent, and does not contain fields outside the allowed list. |
| `REQ-1124` | The test proves that the installation without passports gives `ready` with `detail` calling both commands, and that there is only one owner of the command list. |
| `REQ-1123` | The contract test for search, discover, adopt, status, diff and rollback builds the required parameters and enum from machine help only, checks the existence of each `result_schema`; update plan only accepts the declared value `action=update`. |
