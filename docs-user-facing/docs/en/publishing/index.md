---
title: "Publishing"
description: "How authors publish components and setups in ai_stp."
---

# Publishing

Anyone can publish components and setups. There is no pre-moderation of
publications in the MVP, but provenance, permissions and checks stay visible.

A public version must come from a public GitHub repository at an exact commit
and subpath. Once published, a version is immutable. The version number is
`X.Y`, not SemVer: there is no patch field, and you cannot overwrite `1.0`.

An author can be confirmed by the platform, but that confirms provenance, not
the safety of the content. How to prepare the tree:
[Authoring](authoring.md).

Publication is a signed-in CLI path. The website can show the result; it does
not bind bytes or confirm a plan hash.

## Preconditions

1. Local device identity exists: `ai-stp device init --json`.
2. You are signed in on that same device: `ai-stp auth status --json`.
3. The object is adopted, its passport validates, and an `X.Y` has been
   released locally.
4. The public source is an exact GitHub commit. Branches and short SHAs fail
   closed.
5. Secrets, private paths, and `.env` bodies are absent from the passport and
   the artifact.

```bash
ai-stp component passport validate --id <stable_id> --json
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line instead of the next minor. A major line
is a separate access boundary.

## Sign attestation evidence (optional, exact)

If you have credential-dependent test evidence, sign it with the active
device key **before** planning publication. The file is new; an existing
path is refused.

```bash
ai-stp attestation sign \
  --id <stable_id> \
  --version 1.0 \
  --check-id <check_id> \
  --policy-version <policy> \
  --tool-version <name>=<version> \
  --harness-id <harness> \
  --harness-version <version> \
  --provider-version <version> \
  --test-case-id <case> \
  --result passed \
  --output ./attestation.json \
  --confirm \
  --json
```

`--result` is `passed` or `failed`. Repeat `--tool-version` and
`--test-case-id` as needed. Secret-bearing tool names are refused.

## Publish a released component

Plan, inspect, then confirm the **exact** hash you were shown. Confirming a
lost response is not a second confirm: read status first.

```bash
ai-stp publication plan \
  --id <stable_id> \
  --version 1.0 \
  --attestation-file ./attestation.json \
  --json

ai-stp publication status --plan-id <plan_id> --json

ai-stp publication confirm \
  --plan-id <plan_id> \
  --plan-hash <plan_hash> \
  --confirm \
  --json
```

`--attestation-file` is repeatable and optional. Creating a plan does not
publish. A failed check must not leave a partially published version behind.

## Extract an embedded component, then publish it

A component that exists only inside a setup can be lifted into the ordinary
publication plan:

```bash
ai-stp component publish \
  --from-setup <setup_id> \
  --setup-version 1.0 \
  --component-id <component_id> \
  --json
```

That command materializes the member and creates the usual publication plan.
Confirm it with `publication confirm` as above.

## Publish a setup and every pin

A setup cannot become public before its exact pins. `setup publish` is a
**set**: one plan per unpublished pin, then one for the setup. Already-public
members are listed and not replanned.

```bash
ai-stp setup publish plan --id <setup_id> --version 1.0 --json

ai-stp setup publish confirm --set-digest <set_digest> --confirm --json
```

Confirm walks members in set order: components first, then the setup. A
rejection stops confirmation and moves the set to `partial`. Published
members stay published; a later `setup publish plan` lists them as already
published.

If a confirm response is lost:

```bash
ai-stp publication status --plan-id <plan_id> --json
```

Do not invent a second confirm to discover the outcome.

## Checks

Publication checks the passport, the format, compatibility and whether the
source is reachable. Required safety scans that fail or cannot run block
publication. What the catalog percent means:
[Security checks](../security-checks.md).

## Reports

A problematic object can be reported from the web or the CLI. A report opens a
closed moderation case, not a public discussion.

```bash
ai-stp report preview --kind component --id <id> --version 1.0 --content-digest sha256:... --json
ai-stp report confirm --plan-id <id> --plan-digest <digest> --confirm --json
ai-stp report list --json
```

Details: [Reports](../cli/report.md).

## Related pages

- [Authoring](authoring.md) — how to prepare the tree.
- [Publish a component](../cli/component-publish.md) — adopt, release, plan.
- [Publication](../cli/publication.md) — attest, plan, confirm.
- [Web publication](../web/publications.md) — confirm a CLI-built plan.
- [Security checks](../security-checks.md) — required scans that block.
- [Trust and safety](../trust-and-safety/index.md) — provenance is not safety.
