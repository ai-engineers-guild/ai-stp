---
title: "Trust and safety"
description: "The ai_stp trust model, its confirmations, and the limits of automatic installation."
---

# Trust and safety

`ai_stp` shows provenance, confirmations and constraints. It does not promise
that a published object is safe.

What a catalog scan percent means is on
[Security checks](../security-checks.md). How to file a closed case is on
[Reports](../cli/report.md).

## Two axes of verified

There are two independent axes:

- `author_verified` — the platform confirmed the author or the namespace;
- `component_verified` — the platform confirmed one particular version.

Neither follows from the other. A confirmed author can publish a bad version,
and an unconfirmed author can own a local object you pinned exactly yourself.

## Trust lines

`authoritative` — the ordinary path for objects that may be offered without
consent to experimental risk.

`experimental` — the object may be considered only after the user's explicit
consent.

`local_owner_or_pinned` — the user's own, imported or exactly pinned objects.
They are selected directly after local checks, but they do not thereby become
platform-confirmed.

| Line | May be shown | May be auto-installed | What is asked of you |
| --- | --- | --- | --- |
| `authoritative` | yes | only after the ordinary plan and confirmation | check the meaning and the diff |
| `experimental` | yes, labelled | no, not without explicit consent | accept the experimental risk |
| `local_owner_or_pinned` | yes | only as a locally pinned object | understand that it is not platform-verified |

??? warning "Verified does not transfer responsibility"

    A verified status helps you not to confuse an author or an object. It does
    not replace reading the content. Look especially carefully at `mcp`, `hook`
    and `plugin`, because they can widen permissions or change the target.

## Consent: allow, revoke, list

There is no configuration key that means "include all unverified objects
forever". Consent is either a request marker for one command, or a durable
record for one publisher, one object major line, or the authorized
`full-auto` task profile.

```bash
ai-stp consent allow --scope publisher --target <publisher_id> --json
ai-stp consent allow --scope object_major --target <stable_id>@<major> --json
ai-stp consent allow --scope task --target full-auto --json
ai-stp consent list --json
ai-stp consent revoke --scope publisher --target <publisher_id> --json
```

`--scope` is `publisher`, `object_major`, or `task`. `task` is the
authorized profile, not a wildcard. A `publisher` or `object_major`
target must already have registered objects: an empty fingerprint is
not consent, it is no observation. `task` / `full-auto` does not need
a matching object.

Consent admits candidates into the `experimental` lane. It does not move an
object to `authoritative`, create platform verification, or skip install
checks.

A `publisher` or `object_major` record stops covering a version if that
version needs new permissions, processes, network access, credentials, or
native surfaces compared with the fingerprint stored at consent time. An
active `task` grant still covers that growth. Revocation takes effect
immediately for later requests. A revoked narrower record excludes the
target even when `task` is active.

Search can show the experimental lane for one command without recording
consent:

```bash
ai-stp registry search --kind component --query scanner --include-experimental --json
```

That flag is not stored. Installing still needs a durable consent if the
object is unverified.

Details: [Consent](../cli/consent.md).

## Reports

A problematic public object is a closed moderation case, not a comment thread.

```bash
ai-stp report preview --kind component --id <id> --version 1.0 --content-digest sha256:... --json
ai-stp report confirm --plan-id <id> --plan-digest <digest> --confirm --json
ai-stp report list --json
```

[Reports](../cli/report.md).

## What ai_stp does not do

`ai_stp` does not call model interfaces, does not need a model key, and does
not let an agent get around a mechanical constraint. Only the public provider
writes the harness's final state.

The one outgoing request the CLI makes on its own behalf is an anonymous
install ping, and it is off until you say otherwise. What it contains and how
to turn it off is in [Install telemetry](../cli/telemetry.md).

## Related pages

- [Security checks](../security-checks.md) — what a catalog percent covers.
- [Consent](../cli/consent.md) — durable records, not a search flag.
- [Catalog](../catalog/index.md) — how to read trust on a card.
- [Reports](../cli/report.md) — a closed case, not a comment thread.
- [Quickstart for agents](../quickstart/agent.md) — do not install from a
  headline percent.
- [Publishing](../publishing/index.md) — provenance is not a safety review.
