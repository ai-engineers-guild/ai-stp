---
description: "The ai_stp trust model, its confirmations, and the limits of automatic installation."
---

# Trust and safety

`ai_stp` shows provenance, confirmations and constraints. It does not promise
that a published object is safe.

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

## What ai_stp does not do

`ai_stp` does not call model interfaces, does not need a model key, and does
not let an agent get around a mechanical constraint. Only the public provider
writes the harness's final state.

The one outgoing request the CLI makes on its own behalf is an anonymous
install ping, and it is off until you say otherwise. What it contains and how
to turn it off is in [Install telemetry](../cli/telemetry.md).
