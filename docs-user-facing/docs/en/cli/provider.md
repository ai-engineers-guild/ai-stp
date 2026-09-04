---
title: "Provider"
description: "Check, fetch, trust, and replace the binary that writes native harness state."
---

# Provider

The provider is the public NDDev setup manager for one harness. It is the
only writer of that harness's final state. These commands inspect what is
installed, fetch an attested release, report trust and network isolation,
and replace or reinstall the binary in the same path.

They do not install a setup. After the provider bytes are bound, compose
and apply still go through [Select](select.md) and [Install](install.md).

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp provider check` | `read` | `none` | each harness's installed provider, and whether a newer release exists |
| `ai-stp provider conformance` | `read` | `none` | check one provider against an explicitly selected protocol |
| `ai-stp provider fetch` | `apply` | `none` | download an attested OpenNetwork provider and bind a closed release manifest |
| `ai-stp provider trust` | `read` | `none` | report the pinned trust policy, and check one release against it |
| `ai-stp provider network` | `read` | `none` | observed protocol-v2 network isolation on this machine |
| `ai-stp provider update plan` | `read` | `none` | describe replacing one harness's provider with the newest released version |
| `ai-stp provider update apply` | `apply` | `plan_digest` | carry out exactly the replacement a plan described |
| `ai-stp provider reinstall plan` | `read` | `none` | describe re-installing one exact provider version into the same path |
| `ai-stp provider reinstall apply` | `apply` | `plan_digest` | carry out exactly the reinstallation a plan described |
| `ai-stp provider forget` | `apply` | `none` | drop the recorded provider choice so configuration and discovery decide again |

`--json` is global. Always pass it.

`update plan` and `reinstall plan` are `read`, not `plan`. They describe a
replacement. They do not record an installation operation. Apply is
confirmed by `--expected-plan-digest` of that description. There is no
`--confirm` on this group.

## Check

```bash
ai-stp provider check --json
ai-stp provider check --harness codex --json
ai-stp provider check --harness codex --offline --json
```

`--harness` is repeatable. Omit it for every supported harness.
`--offline` reads what is installed without asking the release source. A
failed request is not reported as "no update".

Success fields: `installations`, `source_consulted`. Each installation has
`harness_id`, `provider_id`, `provider_version`, `path`, `status`,
`source`, `repository`, `latest_tag`, `latest_commit`, `candidates`,
`reason`, `checked_at`.

## Conformance

```bash
ai-stp provider conformance \
  --harness codex \
  --executable <exe> \
  --json
ai-stp provider conformance \
  --harness codex \
  --executable <exe> \
  --target <dir> \
  --protocol-version 3 \
  --unverified-provider \
  --json
```

`--harness` and `--executable` are required. `--protocol-version` defaults
to frozen v1. `--unverified-provider` checks an executable no signed or
attested release covers, such as one you built yourself. Isolation is not
relaxed: the check still runs under the launcher its system proved.

Success fields: `conforms`, `harness_id`, `protocol_version`,
`reported_version`, `cases`. Each case has `name`, `subject`, `passed`,
`exercised`, `detail`.

## Fetch

```bash
ai-stp provider fetch --harness codex --json
ai-stp provider fetch --harness codex --tag <tag> --directory <dir> --json
ai-stp provider fetch \
  --harness codex \
  --artifact <existing-file> \
  --attestation-bundle <bundle> \
  --json
```

`--harness` is required. `--tag` is an exact release tag; omit it to bind
the current GitHub release after resolving its tag. `--directory` receives
the artifact and bound manifest. `--artifact` binds an existing file
instead of downloading. `--attestation-bundle` is an optional local GitHub
attestation bundle for offline verification.

Success fields: `harness_id`, `provider_id`, `provider_version`, `tag`,
`commit`, `repository`, `artifact`, `artifact_digest`, `artifact_url`,
`manifest`, `protocol_version`, `sequence`, `trust_level`.

## Trust and network

```bash
ai-stp provider trust --json
ai-stp provider trust --manifest <release-manifest> --json
ai-stp provider network --json
```

Without `--manifest`, trust reports the pinned policy. With it, the same
answer also says whether that release is accepted.

Trust fields: `policy_id`, `policy_schema_version`, `signature_subject`,
`allowed_keys`, `allowed_publishers`, `allowed_repositories`,
`revoked_keys`, `pinned_releases`, `build_attestations`,
`minimum_sequence`, `known_sequence`, `accepted`, `refusals`.

Network fields: `os_name`, `launcher_id`, `network_enforcement`,
`protocol_version`, `local_actions_available`, `v3_local_phase`,
`v3_local_phase_reasons`, `evidence`.

## Update and reinstall

Both replacement commands take `--harness` (required), `--executable`
(required when more than one provider is installed), and `--adopt`
(replace a provider ai-stp did not install; nothing else overwrites one).
Apply adds `--expected-plan-digest`. Reinstall also takes `--version`: omit
it to reinstall the version already there. Moving to the newest release is
`provider update`, not reinstall.

```bash
ai-stp provider update plan --harness codex --json
ai-stp provider update apply \
  --harness codex \
  --expected-plan-digest sha256:... \
  --json

ai-stp provider reinstall plan --harness codex --version <tag> --json
ai-stp provider reinstall apply \
  --harness codex \
  --version <tag> \
  --expected-plan-digest sha256:... \
  --json
```

When the installed binary was not placed by this CLI:

```bash
ai-stp provider update plan --harness codex --executable <exe> --adopt --json
ai-stp provider update apply \
  --harness codex \
  --executable <exe> \
  --adopt \
  --expected-plan-digest sha256:... \
  --json
```

Plan fields: `operation`, `harness_id`, `path`, `plan_digest`,
`provider_id`, `provider_version`, `current_version`, `current_digest`,
`tag`, `commit`, `repository`, `artifact_url`, `artifact_digest`,
`artifact_bytes`, `backup`, `foreign`, `trust_level`, `idempotency_key`.

Apply fields: `operation`, `outcome`, `harness_id`, `path`, `plan_digest`,
`provider_version`, `previous_version`, `tag`, `artifact_digest`, `backup`.

## Forget

```bash
ai-stp provider forget --json
ai-stp provider forget --harness codex --json
```

`--harness` is repeatable. Omit it for every supported harness. Forget
drops the recorded choice so configuration and discovery decide again. It
does not delete the binary. The answer is the same installations view as
`check`.

## Happy path

```text
provider check
→ provider trust
→ provider fetch --harness <id>
→ provider conformance --harness <id> --executable <exe>
→ install plan --provider <exe> --provider-manifest <path> …
```

Replace a current install:

```text
provider update plan --harness <id>
→ provider update apply --harness <id> --expected-plan-digest sha256:...
→ provider check --harness <id>
```

## Named success fields

| Command | Fields to read |
| --- | --- |
| `check` / `forget` | `installations`, `source_consulted` |
| `conformance` | `conforms`, `cases` |
| `fetch` | `artifact`, `manifest`, `artifact_digest`, `trust_level` |
| `trust` | `accepted`, `refusals`, `policy_id` |
| `network` | `network_enforcement`, `launcher_id`, `v3_local_phase` |
| `update` / `reinstall` plan | `plan_digest`, `path`, `tag`, `backup`, `foreign` |
| `update` / `reinstall` apply | `outcome`, `previous_version`, `provider_version` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | `--harness` or `--expected-plan-digest` missing | read the descriptor |
| `AI_STP_PLAN_STALE` | the bytes on disk no longer match the plan | plan again |
| `AI_STP_USER_DECISION_REQUIRED` | replacing a foreign binary needs `--adopt` | pass `--adopt` after reviewing the path |
| `AI_STP_PRECONDITION_FAILED` | the trust policy refused the release | read `provider trust --manifest`; do not `--unverified-provider` to hide it |
| `AI_STP_DEPENDENCY_UNAVAILABLE` | the release source could not be reached | `--offline` on check, or retry if `retryable: true` |
| `conforms: false` | the executable failed a protocol case | read `cases`; do not install through it |
| `accepted` false | the pinned policy rejected the manifest | stop; do not fetch around the policy |
| inventing `--confirm` | apply is confirmed by `--expected-plan-digest` | pass the digest, not a boolean |

`--unverified-provider` records that the pinned policy checked nothing. It
does not make the binary trusted. Install plans that use it record
`provider_release_trusted` false.

## Related links

- [Install](install.md)
- [Target](target.md)
- [Harness program](harness.md)
- [Toolchain](toolchain.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Harnesses](../harnesses.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups provider commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
