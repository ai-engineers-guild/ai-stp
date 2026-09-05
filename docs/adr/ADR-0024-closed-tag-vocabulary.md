---
description: "Decision to publish tags only from a closed, versioned vocabulary."
last_verified: "2026-09-04"
---

# ADR-0024: Tags come from a closed vocabulary

Status: accepted.

## Context

A published version must have a non-empty tag list: tags participate in search and structural filters alongside object kind and compatibility. But the “non-empty normalized list” rule does not answer where the values come from.

Free-form tags in a catalog read by an agent fragment predictably. The same meaning acquires `python`, `python3`, `py`, `Python`, and the Russian word for Python; case and hyphen normalization cannot fix this because the words, not their spellings, differ. The filter ceases to function as a filter: the agent cannot ask to “show everything for Python” without listing synonyms it does not know. This then creates shadow work to merge synonyms and moderate junk tags, for which no one is responsible in the MVP.

The primary consumer here is an agent, not a human, and that changes the balance. A human forgives inconsistency and infers meaning; an agent selects by exact match and silently loses candidates.

## Options

1. Free-form normalized tags. This costs nothing initially, but the filter becomes unreliable and vocabulary cleanup becomes constant manual work.
2. Free-form tags plus separate “official” tags. This creates two entities with the same name and raises the question of which ones participate in filtering.
3. A closed, versioned vocabulary maintained by the platform.

## Decision

Option 3 is accepted.

**Tags come only from the vocabulary.** Publication with a tag outside the vocabulary is rejected with a typed error that names the unknown value and the nearest permitted values.

**The vocabulary is machine-readable and available.** It is exposed through both the CLI and API, so the agent selects tags from the list instead of inventing them. Each vocabulary entry has a stable identifier, display name, optional description, and optional search synonyms.

**Synonyms work for reading, not writing.** Searching by a synonym finds an object; the tag's canonical identifier is always stored in the passport.

**The vocabulary is versioned.** Adding a value is compatible; renaming a display name does not change the identifier; deleting a value is prohibited—instead, the entry is marked deprecated and no longer offered during publication, without breaking already published versions.

**Extension is a separate process.** Platform owners add a new value. Until it exists, the author selects the nearest existing one; the absence of a desired tag does not block publication as a whole.

**Per-object limit.** The number of tags on one version is limited so that a tag remains a filter rather than a description.

## Consequences

- `contracts/tag-vocabulary.md` is introduced as the owner of the vocabulary format, validation, and limit;
- `SPEC-005` and `SPEC-007` require tags to belong to the vocabulary at publication time;
- search filters by canonical identifier and finds by synonym;
- the CLI and API expose the vocabulary, and the Agent Skill selects tags from it;
- a cold catalog start requires populating the vocabulary before the first publication.

## Reconsideration conditions

The decision shall be reconsidered if maintaining the vocabulary becomes a publication bottleneck—authors regularly lack a value and owners cannot extend it quickly enough.
