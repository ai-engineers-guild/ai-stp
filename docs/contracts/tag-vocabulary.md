---
description: "Tag vocabulary format, validation, limit, and search behavior."
last_verified: "2026-09-04"
---

# Tag vocabulary

The decision owner is `ADR-0024`, and the requirements owners are `SPEC-005` and
`SPEC-007`. This document defines the machine boundary: vocabulary entry form,
validation rules, the limit, and what enters a passport.

## Vocabulary entry

```yaml
schema_version: 1
vocabulary_version: "1.0"
tags:
  - id: "python"
    name: "Python"
    description: "Projects and components for Python."
    aliases: ["py", "python3"]
    status: active
  - id: "code-review"
    name: "Code review"
    aliases: ["review"]
    status: active
```

The `id` field is the canonical value: it is stored in the passport and used for
filtering. `name` is for display and may change without changing `id`. `aliases`
participate only in search.

The `status` field accepts `active` and `deprecated`. A deprecated entry is not offered
during publication but remains valid in already published versions and remains
searchable. Deleting an entry is prohibited.

## Validation

A tag identifier:

- consists only of lowercase English letters (`a-z`), digits (`0-9`), and
  hyphens (`-`);
- neither starts nor ends with a hyphen and contains no two consecutive hyphens;
- is from two to thirty-two ASCII characters long;
- uses hyphens instead of spaces.

Typography and non-English letters are prohibited. A value that fails this form
is rejected before comparison with the vocabulary: invalid form and unknown
value are distinct errors.

## Limit

One object version declares at least one and at most ten tags. A repeated identifier
in the list is rejected. Tag order is insignificant and is canonicalized into ascending
identifier order.

## Publication

Publication is rejected if the tag list is empty, contains a value outside the
vocabulary, contains a deprecated entry newly introduced by this version, or exceeds
the limit. The error names the unknown value and the nearest permitted vocabulary entries.

Local registration without publication is not constrained by the vocabulary: it does
not enter the shared catalog or participate in another user's search.

## Search

The tag filter operates on the canonical identifier. A search query is additionally
matched against `name` and `aliases`, but the result is always described by identifiers.

## Versioning and distribution

The vocabulary is versioned separately from the passport schema: adding an entry is
compatible and does not require a new schema version. The single source is
`ai_stp_contracts.tag_vocabulary`. Anonymous `GET /v1/catalog/tags` returns it.
The CLI imports the same module. Offline operation uses that in-process copy.
Web facets are generated from it together with `HARNESS_ID_ORDER`.
