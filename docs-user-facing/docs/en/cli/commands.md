---
title: "Command map"
description: "Every ai-stp command, grouped by help-center page. Flags come from machine help."
---

# Command map

The table lists every command declared in the running CLI registry.
Flags, parameter rules, and `next_actions` are not copied here: they change with
the installed version. Read them from the CLI:

```bash
ai-stp help --agent --json
```

`mutability` says what the command does. `confirmation` says which token proves
the decision. Neither is a substitute for reading the descriptor before a call.

The executable is `ai-stp`. The PyPI package is `ai-stp-cli`.

| Command | Mutability | Confirmation | Owner page | What it is for |
| --- | --- | --- | --- | --- |
| `ai-stp eval profile` | `read` | `none` | [eval.md](eval.md) | Show the versioned reference evaluation profile for all or one component type. |
| `ai-stp eval plan` | `plan` | `none` | [eval.md](eval.md) | Bind a reference evaluation profile to one exact local setup graph. |
| `ai-stp eval run` | `apply` | `plan_digest` | [eval.md](eval.md) | Run local deterministic checks for one confirmed exact evaluation plan. |
| `ai-stp eval status` | `read` | `none` | [eval.md](eval.md) | Read the immutable status of one local evaluation run. |
| `ai-stp eval show` | `read` | `none` | [eval.md](eval.md) | Show full immutable local evidence for one evaluation run. |
| `ai-stp publication plan` | `plan` | `none` | [publication.md](publication.md) | Create an immutable server plan for one exact released component version. |
| `ai-stp attestation sign` | `apply` | `explicit_flag` | [publication.md](publication.md) | Sign exact credential-dependent test evidence with the active device key. |
| `ai-stp publication status` | `read` | `none` | [publication.md](publication.md) | Read the current server state of one publication plan. |
| `ai-stp publication confirm` | `apply` | `explicit_flag` | [publication.md](publication.md) | Confirm one exact unexpired publication plan hash. |
| `ai-stp grant list` | `read` | `none` | [grant.md](grant.md) | List invitations and major-line grants owned by the current account. |
| `ai-stp grant invite` | `apply` | `explicit_flag` | [grant.md](grant.md) | Create an email invitation for one exact object major line. |
| `ai-stp grant direct` | `apply` | `explicit_flag` | [grant.md](grant.md) | Grant one exact object major line to an explicit account identifier. |
| `ai-stp grant accept` | `apply` | `explicit_flag` | [grant.md](grant.md) | Accept an invitation using a token read from a named environment variable. |
| `ai-stp grant invitation revoke` | `destructive` | `explicit_flag` | [grant.md](grant.md) | Revoke one pending invitation without deleting local bytes. |
| `ai-stp grant revoke` | `destructive` | `explicit_flag` | [grant.md](grant.md) | Revoke one active grant forward-only while retaining local bytes. |
| `ai-stp report preview` | `plan` | `none` | [report.md](report.md) | Prepare and show the exact bounded report payload without sending it. |
| `ai-stp report confirm` | `apply` | `explicit_flag` | [report.md](report.md) | Submit one exact durable report preview after explicit confirmation. |
| `ai-stp report list` | `read` | `none` | [report.md](report.md) | List the current account's closed report cases. |
| `ai-stp owner objects` | `read` | `none` | [owner.md](owner.md) | List objects owned by the authenticated account. |
| `ai-stp owner object show` | `read` | `none` | [owner.md](owner.md) | Read one server-authorized owned object and its exact versions. |
| `ai-stp owner version show` | `read` | `none` | [owner.md](owner.md) | Read one exact owned version and its server lifecycle evidence. |
| `ai-stp auth complete` | `apply` | `none` | [auth.md](auth.md) | Finish the pending sign-in once the user has approved it. |
| `ai-stp auth login` | `apply` | `none` | [auth.md](auth.md) | Start a sign-in and report the code the user must approve. |
| `ai-stp auth logout` | `apply` | `none` | [auth.md](auth.md) | End the cloud session on the server and here, keeping all local data. |
| `ai-stp auth status` | `read` | `none` | [auth.md](auth.md) | Report the platform relationship: local-only, authenticated, expired or revoked. |
| `ai-stp capabilities` | `read` | `none` | [observe.md](observe.md) | Report what this installation can do right now. |
| `ai-stp component discover` | `read` | `none` | [component-discover.md](component-discover.md) | List native components in the harness roots and one project. Changes nothing. |
| `ai-stp component scaffold plan` | `plan` | `none` | [component-discover.md](component-discover.md) | Preview exact files and digests for one versioned component scaffold. |
| `ai-stp component scaffold apply` | `apply` | `plan_digest` | [component-discover.md](component-discover.md) | Create exactly the confirmed component scaffold without overwriting a path. |
| `ai-stp component template render` | `read` | `none` | [component-discover.md](component-discover.md) | Render and validate a portable template for one concrete harness. |
| `ai-stp component source parse` | `read` | `none` | [component-source.md](component-source.md) | Parse an external component source as untrusted structured intent. |
| `ai-stp component source resolve` | `read` | `none` | [component-source.md](component-source.md) | Bind a GitHub source intent to one exact full commit SHA. |
| `ai-stp component source search` | `read` | `none` | [component-source.md](component-source.md) | Search catalog names; package and GitHub hits need --registry-discovery. |
| `ai-stp component publish` | `plan` | `none` | [component-publish.md](component-publish.md) | Extract one embedded component into the ordinary publication plan. |
| `ai-stp component source evidence refresh` | `apply` | `none` | [component-source.md](component-source.md) | Refresh official GitHub archived evidence for one exact local version. |
| `ai-stp component source evidence show` | `read` | `none` | [component-source.md](component-source.md) | Show the latest local GitHub archived evidence and freshness. |
| `ai-stp component source evidence history` | `read` | `none` | [component-source.md](component-source.md) | Show bounded append-only GitHub archived evidence history. |
| `ai-stp component adopt` | `apply` | `none` | [component-discover.md](component-discover.md) | Register one discovered component in the local registry. |
| `ai-stp component passport show` | `read` | `none` | [component-passport.md](component-passport.md) | Show the current local passport draft for one adopted component. |
| `ai-stp component passport suggest` | `read` | `none` | [component-passport.md](component-passport.md) | Suggest exact manifest facts for confirmation without changing the draft. |
| `ai-stp component passport update` | `apply` | `plan_digest` | [component-passport.md](component-passport.md) | Add confirmed declared facts as a new content-addressed passport revision. |
| `ai-stp component passport validate` | `read` | `none` | [component-passport.md](component-passport.md) | Report every structural blocker to publishing the current passport revision. |
| `ai-stp component passport quality` | `read` | `none` | [component-passport.md](component-passport.md) | Show optional mechanical authoring hints without changing trust or readiness. |
| `ai-stp component forget` | `apply` | `none` | [component-discover.md](component-discover.md) | Mark a registered component deleted, keeping its history. |
| `ai-stp consent allow` | `apply` | `none` | [consent.md](consent.md) | Record consent to unverified objects of one publisher or major line. |
| `ai-stp consent revoke` | `apply` | `none` | [consent.md](consent.md) | Withdraw a consent. Takes effect immediately for later requests. |
| `ai-stp consent list` | `read` | `none` | [consent.md](consent.md) | Every consent still in force, and what each covered when given. |
| `ai-stp component version list` | `read` | `none` | [component-publish.md](component-publish.md) | Every recorded version of one object, and the next minor number. |
| `ai-stp component version release` | `apply` | `none` | [component-publish.md](component-publish.md) | Give the current head an immutable X.Y number. Minor unless told otherwise. |
| `ai-stp component fork` | `apply` | `none` | [component-publish.md](component-publish.md) | Copy one recorded version under a new identity. The original is untouched. |
| `ai-stp component find` | `read` | `none` | [component-discover.md](component-discover.md) | Search the local registry by prefix, phrase, tag or field. No model, no network. |
| `ai-stp config init` | `apply` | `none` | [config.md](config.md) | Create the configuration file if it is absent, and validate it either way. |
| `ai-stp config set` | `apply` | `none` | [config.md](config.md) | Write declared values to the configuration file. |
| `ai-stp config unset` | `apply` | `none` | [config.md](config.md) | Remove declared values so their defaults apply again. |
| `ai-stp config validate` | `read` | `none` | [config.md](config.md) | Read the configuration file and refuse it if it cannot be honoured. |
| `ai-stp config show` | `read` | `none` | [config.md](config.md) | Show the effective configuration and where each value came from. |
| `ai-stp device reset` | `destructive` | `explicit_flag` | [device.md](device.md) | Retire this device identity and create a new one. |
| `ai-stp device init` | `apply` | `none` | [device.md](device.md) | Create the identity of this installation, or return the existing one. |
| `ai-stp device show` | `read` | `none` | [device.md](device.md) | Show this device identity and where its key is kept. |
| `ai-stp doctor` | `read` | `none` | [observe.md](observe.md) | Report the setup state of this installation without changing it. |
| `ai-stp help` | `read` | `none` | [observe.md](observe.md) | Emit the full command registry for an agent. |
| `ai-stp link web` | `read` | `none` | [auth.md](auth.md) | Print a canonical web URL and round-trippable CLI reference. |
| `ai-stp passport developer init` | `apply` | `none` | [passport.md](passport.md) | Create the developer passport of this installation. |
| `ai-stp passport developer show` | `read` | `none` | [passport.md](passport.md) | Show the developer passport at its current head. |
| `ai-stp passport developer update` | `apply` | `none` | [passport.md](passport.md) | Declare developer facts, adding one revision. |
| `ai-stp passport device refresh` | `apply` | `none` | [passport.md](passport.md) | Create this device passport, or bring it up to what is observable now. |
| `ai-stp passport device show` | `read` | `none` | [passport.md](passport.md) | Show this device passport at its current head. |
| `ai-stp project discover` | `read` | `none` | [project.md](project.md) | List the projects inside a directory you name. Scans nothing else. |
| `ai-stp project index` | `read` | `none` | [project.md](project.md) | Index one project root, bounded, skipping secrets and binary content. |
| `ai-stp project symbols` | `read` | `none` | [project.md](project.md) | Read a project's public symbols, entry points and tests. No call graph. |
| `ai-stp harness install` | `apply` | `none` | [harness.md](harness.md) | Install the harness program itself under an exact prefix. |
| `ai-stp harness update` | `apply` | `none` | [harness.md](harness.md) | Move the exposed harness program to the version its provider pins. |
| `ai-stp harness remove` | `destructive` | `explicit_flag` | [harness.md](harness.md) | Remove the harness program this CLI installed, and nothing else. |
| `ai-stp harness resume` | `apply` | `none` | [harness.md](harness.md) | Settle a stopped program operation by looking, never by applying again. |
| `ai-stp harness status` | `read` | `none` | [harness.md](harness.md) | What program stands under one prefix, from the journal and the disk. |
| `ai-stp toolchain install` | `apply` | `none` | [toolchain.md](toolchain.md) | Install one pinned tool into the managed directory. Runs nothing from it. |
| `ai-stp toolchain remove` | `destructive` | `explicit_flag` | [toolchain.md](toolchain.md) | Remove one managed tool, touching only paths this CLI created. |
| `ai-stp project passport` | `apply` | `none` | [project.md](project.md) | Record a project passport revision pinning the index, toolchain and config. |
| `ai-stp registry acquire` | `apply` | `none` | [registry.md](registry.md) | Acquire one exact published setup graph for local offline compilation. |
| `ai-stp registry port discover` | `read` | `none` | [registry.md](registry.md) | Find compatible SX and APM snapshots under one explicit local root. |
| `ai-stp registry port inspect` | `read` | `none` | [registry.md](registry.md) | Inspect one setup-store mapping without importing or running its CLI. |
| `ai-stp registry port plan` | `plan` | `none` | [registry.md](registry.md) | Preview a local-only setup-store import and bind it to exact manifest bytes. |
| `ai-stp registry port import` | `apply` | `plan_digest` | [registry.md](registry.md) | Import a confirmed exact SX or APM snapshot into the local registry only. |
| `ai-stp registry fetch` | `apply` | `none` | [registry.md](registry.md) | Fetch the exact bytes of one published version into the local cache. |
| `ai-stp registry search` | `read` | `none` | [registry.md](registry.md) | Search the public catalogue without an account. |
| `ai-stp registry version` | `read` | `none` | [registry.md](registry.md) | Show one exact published version and its verified passport. |
| `ai-stp registry show` | `read` | `none` | [registry.md](registry.md) | Show one catalogue object and its published versions. |
| `ai-stp select eligibility` | `read` | `none` | [select.md](select.md) | Which candidates a harness may be composed from, and why each refusal happened. |
| `ai-stp select eligibility-matrix` | `read` | `none` | [select.md](select.md) | Where one object may be composed, answered for every supported harness. |
| `ai-stp select impact` | `read` | `none` | [select.md](select.md) | Compare context, token cost and capabilities of exact local setup versions. |
| `ai-stp select blast-radius` | `read` | `none` | [select.md](select.md) | Show local setup, project, device and installed-target references to a component. |
| `ai-stp select propose` | `plan` | `none` | [select.md](select.md) | Record one composition proposal. Creates no version and no target. |
| `ai-stp select confirm` | `apply` | `none` | [select.md](select.md) | Freeze one proposal as a private setup version, its trace and its pin. |
| `ai-stp select cancel` | `apply` | `none` | [select.md](select.md) | Close one proposal without creating a version or changing a target. |
| `ai-stp select graph` | `read` | `none` | [select.md](select.md) | Resolve the exact dependency closure, or name every reason it cannot be. |
| `ai-stp select reports` | `read` | `none` | [select.md](select.md) | Composition and conversion reports: what is chosen, what conflicts, what is lost. |
| `ai-stp select bundle` | `read` | `none` | [select.md](select.md) | Compile the deterministic package for one composition. Writes to no target. |
| `ai-stp install plan` | `plan` | `none` | [install.md](install.md) | Compute an immutable installation plan. Has no effect of its own. |
| `ai-stp install approve` | `apply` | `plan_digest` | [install.md](install.md) | Approve one plan by its exact digest. Nothing else approves it. |
| `ai-stp install apply` | `apply` | `plan_digest` | [install.md](install.md) | Carry out one approved plan through its provider and record what happened. |
| `ai-stp install cancel` | `apply` | `none` | [install.md](install.md) | Abandon a plan before anything is applied. Refused once applying began. |
| `ai-stp target status` | `read` | `none` | [target.md](target.md) | The daily state of one project and harness. Reads; never updates anything. |
| `ai-stp sync preview` | `read` | `none` | [sync.md](sync.md) | Preview local fast-forward, merge or conflict without changing a head. |
| `ai-stp sync push` | `apply` | `explicit_flag` | [sync.md](sync.md) | Push one exact local head with a durable replay-safe event. |
| `ai-stp sync merge` | `apply` | `explicit_flag` | [sync.md](sync.md) | Commit a mechanically clean merge of two developer-passport heads. |
| `ai-stp sync pull` | `apply` | `explicit_flag` | [sync.md](sync.md) | Pull and atomically apply one bounded page from the account stream. |
| `ai-stp target diff` | `read` | `none` | [target.md](target.md) | What installing the selected version would change. Changes nothing. |
| `ai-stp telemetry show` | `read` | `none` | [telemetry.md](telemetry.md) | What the anonymous install ping would carry, and whether it is on. |
| `ai-stp telemetry consent` | `apply` | `explicit_flag` | [telemetry.md](telemetry.md) | Answer the telemetry screen. Sends nothing itself. |
| `ai-stp target backups` | `read` | `none` | [target.md](target.md) | Provider-owned copies this pair can restore from. Restores nothing itself. |
| `ai-stp target rollback` | `read` | `none` | [target.md](target.md) | Name the exact previous verified version. Rolls nothing back itself. |
| `ai-stp install status` | `read` | `none` | [install.md](install.md) | Operations that stopped without a settled outcome. Changes nothing. |
| `ai-stp install recover` | `read` | `none` | [install.md](install.md) | What one stopped operation left, and what may be done. Recovers nothing itself. |
| `ai-stp install resume` | `apply` | `none` | [install.md](install.md) | Finish the result check an interrupted apply never made. Applies nothing. |
| `ai-stp setup compose plan` | `plan` | `none` | [setup.md](setup.md) | Resolve and freeze a new setup from exact catalog, Git, package and local sources. |
| `ai-stp setup compose apply` | `apply` | `explicit_flag` | [setup.md](setup.md) | Record the exact still-current mixed setup as one immutable local version. |
| `ai-stp setup import inspect` | `read` | `none` | [setup.md](setup.md) | Read one native configuration and report what it holds. Writes nothing. |
| `ai-stp setup import plan` | `plan` | `none` | [setup.md](setup.md) | Plan exact component and setup drafts from one native configuration. |
| `ai-stp setup publish plan` | `plan` | `none` | [setup.md](setup.md) | Plan the publication of one released setup together with every component it pins. |
| `ai-stp setup publish confirm` | `apply` | `explicit_flag` | [setup.md](setup.md) | Confirm one exact reviewed publication set: pinned components, then the setup. |
| `ai-stp setup update plan` | `plan` | `none` | [setup.md](setup.md) | Preview replacing one embedded component with a newer exact snapshot. |
| `ai-stp setup update apply` | `apply` | `explicit_flag` | [setup.md](setup.md) | Confirm one exact embedded update and create a new immutable setup version. |
| `ai-stp setup import register` | `apply` | `plan_digest` | [setup.md](setup.md) | Register an inspected configuration as your own setup. No secret value is stored. |
| `ai-stp provider conformance` | `read` | `none` | [provider.md](provider.md) | Check one provider against an explicitly selected protocol. Changes nothing. |
| `ai-stp component skill validate` | `read` | `none` | [component-publish.md](component-publish.md) | Check a skill package against the Agent Skills Specification and name every deviation. Changes nothing. |
| `ai-stp provider check` | `read` | `none` | [provider.md](provider.md) | Report each harness's installed setup-system provider and whether a newer release exists. Changes nothing. |
| `ai-stp provider update plan` | `read` | `none` | [provider.md](provider.md) | Describe replacing one harness's provider with the newest released version, in the same path. Changes nothing. |
| `ai-stp provider update apply` | `apply` | `plan_digest` | [provider.md](provider.md) | Carry out exactly the provider replacement a plan described. |
| `ai-stp provider reinstall plan` | `read` | `none` | [provider.md](provider.md) | Describe re-installing one exact provider version into the same path. Changes nothing. |
| `ai-stp provider reinstall apply` | `apply` | `plan_digest` | [provider.md](provider.md) | Carry out exactly the provider reinstallation a plan described. |
| `ai-stp provider forget` | `apply` | `none` | [provider.md](provider.md) | Drop the recorded provider choice so configuration and discovery decide again. |
| `ai-stp provider fetch` | `apply` | `none` | [provider.md](provider.md) | Download an attested OpenNetwork provider and bind a closed release manifest. |
| `ai-stp provider network` | `read` | `none` | [provider.md](provider.md) | Report observed protocol-v2 network isolation on this machine. |
| `ai-stp provider trust` | `read` | `none` | [provider.md](provider.md) | Report the pinned provider trust policy, and check one release against it. |
| `ai-stp select session` | `read` | `none` | [select.md](select.md) | Open proposals for one project and harness, and the version selected. |
| `ai-stp skill install` | `apply` | `none` | [skill.md](skill.md) | Install the canonical Agent Skill at a named destination. |
| `ai-stp skill remove` | `apply` | `none` | [skill.md](skill.md) | Remove the Agent Skill this installation put at a destination. |
| `ai-stp skill status` | `read` | `none` | [skill.md](skill.md) | Report what Agent Skill is at a destination and who owns it. |
| `ai-stp toolchain harness-capabilities` | `read` | `none` | [toolchain.md](toolchain.md) | Per harness and kind: what the product natively reads, what this build can project, and why any gap is a gap. Not a claim that a component is active — ask the provider for that. |
| `ai-stp toolchain harnesses` | `read` | `none` | [toolchain.md](toolchain.md) | Report every supported harness and whether it is on this machine. |
| `ai-stp toolchain profile` | `read` | `none` | [toolchain.md](toolchain.md) | Show the managed toolchain profile as it resolves on this machine. |
| `ai-stp version` | `read` | `none` | [observe.md](observe.md) | Report the running build and the contract versions it speaks. |

The session ritual that uses this table is
[Quickstart for agents](../quickstart/agent.md). Envelopes and mutability:
[CLI](index.md). Observe commands:
[Observe](observe.md).

!!! note
    If `help --agent` names a command that is missing from this table, the installed CLI is newer than this page: follow the CLI.
