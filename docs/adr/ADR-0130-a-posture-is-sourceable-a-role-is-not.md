---
description: "Decision to make target_role optional and introduce posture as a first-class setup passport field, because a posture can be sourced while a role cannot."
last_verified: "2026-08-30"
---

# ADR-0130: A posture is sourceable; a role is not

Status: accepted.

## Context

No accepted record or specification names the `target_role` field: a search of
`docs/adr/` and `specs/active/` finds it nowhere except this record. It appeared
in the model without a decision. This is not an amendment to someone else's
choice, but the first time the choice has been recorded—and part of the
explanation for why the field became mandatory without a source.

The catalog returned **26** setups: seven active and nineteen `deprecated`.
This was measured by traversing the deployed `/v1/catalog/setups` to the end,
not just its first page.

The seven active setups carried `target_role: "ai-harness-engineer"`. This string
is set by `packages/contracts/src/ai_stp_contracts/first_party/__init__.py:299`
and does not occur in any file on the publishing side—as confirmed by another
search across all seven repositories. The field is rendered on the catalog card
and the version page, so it is a claim about someone else's artifact that every
visitor reads.

Twelve of the nineteen `deprecated` entries are setups for the roles `backend`,
`frontend`, `full-stack`, `code-review`, `security`, and `research`. Neither side
planned them; the test that required six roles was removed in `e1560b41` as
describing something nonexistent.

The real axis that distinguishes setups for the same harness is **posture**:
`minimal`, `baseline`, `full-auto`, `nddev-builder`. It is published: every
`setups/<posture>/setup.json` carries an `"id"` with exactly that string, across
all 7×4.

## Why the field proved impossible to populate

A posture is sourceable: every `setup.json` lists the vendor pages from which
the posture was assembled. A role is a claim about **content**, and there is
nothing to substantiate it: no vendor page says anything about roles. The
publishing side does not publish roles and did not plan them—that is their
decision, not an omission.

This yields the general form of the defect, which matters more than this case:
**a mandatory field that no source can populate is a field that forces
fabrication.**

The tree itself proves that fabrication was forced. Of the four places that
populate `target_role`, three already put something other than a role there:

| location | value |
|---|---|
| `first_party/__init__.py:299` | `ai-harness-engineer` — fabricated |
| `local/setup_versions.py:95` | `local-project` |
| `provider/bundle_corpus.py:195` | `provider-conformance` |
| `catalog_seed.py` | `on-call-engineer`, `platform-engineer` — actual roles |

Actual roles exist only in demonstration seeds. Everything else is a free-form
label for “what this is,” written into a field named `target_role`.

## Considered options

**Put the posture in `target_role`.** Rejected. On a card, a reader could make
reasonable sense of `full-auto` under “Target role,” but the field name would
become a lie, and `ADR-0015` describes a role. One word, one object.

**Remove `target_role` entirely.** Rejected. The field is published, it has
nonempty values in seeds, and removal would break readers over something that
optionality solves. A role remains meaningful for a setup whose author declares
one.

**Keep it mandatory and populate it with the posture during import.** This is
the current behavior under another name: the mechanism that forces fabrication
remains.

**Make `target_role` optional and introduce `posture`.** Accepted.

## Decision

`target_role` becomes optional (`str | None`). First-party import does not set
it: it does not know the role and has no source that names one.

`posture` is introduced as a first-class setup passport field. It is not part
of the name string: it is the axis by which a user chooses among four cards for
one harness, and hiding it in the name would turn the choice into a string
search. The value comes from the published `"id"`, not from the path segment; a
directory whose `setup.json` declares a different `id` is rejected loudly.

`name` and `description` also cease to be invented and come from the source.
Depending on the harness, the `full-auto` description ranges from 690 to 3312
characters; it carries essential security context, stating, for example, that
the sandbox key has no effect on native Windows. The browsing card may truncate
it; the installation surface may not.

An absence of `sources` is recorded as a claim rather than an omission: five of
the seven `minimal` setups define no product keys, so there is nothing to source.

## Consequences

The **published** contract changes: the passport model, generated schemas,
catalog projection, generated client, and two web pages. The card gains a
“posture” line beside the role, and the role is empty for first-party setups,
which is honest: nobody declared one.

The catalog is reseeded: 28 setups instead of 7; twelve role-based entries and
seven superseded `v1.0` entries are withdrawn.

The cost, stated directly: existing readers treated `target_role` as mandatory,
and `None` is a new state that every one of them must be able to display. This
is exactly the class of change in which a field discovers its readers one by
one, so all of them are listed in the same change rather than as they are found.

## Reconsideration conditions

Reconsider if a source to which a role can be sourced appears; the field would
then become mandatory again for objects that have such a source, not for all
objects.
