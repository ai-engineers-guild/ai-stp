# Security policy

## Reporting a vulnerability

Do not disclose vulnerability details in a public issue. Use GitHub Private Vulnerability Reporting on this repository's **Security** tab.

Reports about published catalog objects are submitted through the product and create a private moderation case under `SPEC-016`; moderators escalate a case showing signs of a vulnerability into this private process without disclosing details.

Include the affected version or commit, minimal reproduction steps, expected and actual behavior, potential impact, and safe evidence without real secrets.

## Assets

Protected assets include private setup and component artifacts; OAuth, session, and device keys; the user's file system and harness targets; passports and project data; publication authorship; provider releases; administrative access; and the operation journal.

## Untrusted inputs

Untrusted inputs include the contents of external repositories and archives, uploaded artifacts, third-party manifests and passports, remote MCPs and their responses, OAuth callbacks, provider and scanner output, synchronization events, administrative actions, and issues, PRs, commit messages, and documentation.

## Actors considered

These include a regular user, author, unverified author, revoked device, administrator, malicious artifact, repository or MCP, compromised provider release, and a process belonging to the same user that ignores coordinated locks.

## Primary threats

Path traversal and unsafe extraction, replacement through symbolic or hard links, command or model-instruction injection, malicious hooks, scripts, and plugins, secret extraction, SSRF through external endpoints, bypassing user or object authorization, device event replay, forged attestation, dependency or provider substitution, stale plans, partial application, lost concurrent updates, stored XSS in descriptions, and resource exhaustion.

## Three independent axes

The agent execution profile within the harness, isolation of validation-tool execution, and integrity of the mutating operation are three independent axes under `ADR-0017`. The `full-auto` profile applies only to the first axis and does not waive authorization, artifact validation, planning, backup, atomicity, or recovery.

## Mandatory protections

- a published version is bound to an exact source revision and digest;
- traversal, unsafe symlinks and hardlinks, and special devices are rejected;
- arbitrary post-install scripts are denied by default;
- an external tool is launched with an argument array, without a shell, by exact path, with a timeout and output limit;
- validations run without network access by default;
- an error, `degraded`, or `not_run` result is not converted into `passed`;
- policy defines the mandatory validation set by object kind and transport class, and an unknown value fails closed;
- a remote connection endpoint is validated separately from the local package, including server-side request forgery protection;
- a verified author is not an automatic security verdict and does not make a version verified;
- environment-variable values are not read; only the presence of a name is checked;
- knowledge of an account identifier or email address does not grant authority;
- an agent does not confirm its own external write;
- a `sudo` password is never passed to the agent, CLI, as an argument, through stdin, or through the environment;
- authorization is checked for every object and action, and administrative access is logged;
- device revocation, nonces, and idempotency keys protect against replay;
- the plan/revalidate/journal cycle and an isolated target precede every write;
- web output is safely encoded, with CSP, rate limits, and resource limits applied;
- device tokens and keys are not stored in passports;
- unknown states are typed and are not reduced to success.

## Explicit limitation

Intentional file modification by another process of the same user outside the coordinated protocol is not considered proven to be prevented.

## Supported versions

Until the first public release, only the current version from the default branch is supported. After the first release, the support window for major lines will be recorded here.
