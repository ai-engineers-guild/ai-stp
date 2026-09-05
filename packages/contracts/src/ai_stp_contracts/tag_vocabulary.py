"""Single versioned catalog tag vocabulary (ADR-0024, docs/contracts/tag-vocabulary.md).

This module is the machine-readable source. The HTTP resource, CLI imports,
seed corpus, search aliases, and the generated web facet list all read it.
Display names may change; identifiers do not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_passports.versions import MAX_TAG_LENGTH, MAX_TAGS, TAG_PATTERN, TagId

VOCABULARY_VERSION: Final[str] = "1.0"
TagStatus = Literal["active", "deprecated"]


@dataclass(frozen=True, slots=True)
class TagVocabularyEntry:
    """One closed-vocabulary tag."""

    id: str
    name: str
    aliases: tuple[str, ...] = ()
    description: str | None = None
    status: TagStatus = "active"


TAG_VOCABULARY: Final[tuple[TagVocabularyEntry, ...]] = (
    TagVocabularyEntry(
        id="python",
        name="Python",
        aliases=("py", "python3"),
        description="Projects and components for Python.",
    ),
    TagVocabularyEntry(
        id="tests",
        name="Tests",
        aliases=("testing",),
        description="Automated tests, fixtures, and test runners.",
    ),
    TagVocabularyEntry(
        id="code-review",
        name="Code review",
        aliases=("review",),
        description="Reviewing diffs, pull requests, and patches.",
    ),
    TagVocabularyEntry(
        id="documentation",
        name="Documentation",
        aliases=("docs",),
        description="Guides, references, and in-product help.",
    ),
    TagVocabularyEntry(
        id="devops",
        name="DevOps",
        aliases=("ci",),
        description="Build, deploy, and operations workflows.",
    ),
    TagVocabularyEntry(
        id="security",
        name="Security",
        aliases=("sec",),
        description="Hardening, scanning, and safe defaults.",
    ),
    TagVocabularyEntry(
        id="refactor",
        name="Refactor",
        aliases=("cleanup",),
        description="Structural cleanup without changing behaviour.",
    ),
    TagVocabularyEntry(
        id="github",
        name="GitHub",
        aliases=(),
        description="GitHub repositories, Actions, and related workflows.",
    ),
    TagVocabularyEntry(
        id="planning",
        name="Planning",
        aliases=("plan",),
        description="Task breakdown, roadmaps, and planning agents.",
    ),
    TagVocabularyEntry(
        id="release",
        name="Release",
        aliases=("publish",),
        description="Versioning, packaging, and release evidence.",
    ),
)

TAG_IDS: Final[tuple[str, ...]] = tuple(entry.id for entry in TAG_VOCABULARY)
_BY_ID: Final[dict[str, TagVocabularyEntry]] = {entry.id: entry for entry in TAG_VOCABULARY}
_ALIAS_TO_ID: Final[dict[str, str]] = {}
for _entry in TAG_VOCABULARY:
    _ALIAS_TO_ID[_entry.id] = _entry.id
    _ALIAS_TO_ID[_entry.name.casefold()] = _entry.id
    for _alias in _entry.aliases:
        _ALIAS_TO_ID[_alias.casefold()] = _entry.id


class TagVocabularyItem(BaseModel):
    """One vocabulary entry on the wire."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    id: TagId
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=320)
    aliases: list[str] = Field(default_factory=list[str], max_length=16)
    status: TagStatus = "active"


class TagVocabularyResponse(BaseModel):
    """Versioned closed tag vocabulary (ADR-0024)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    vocabulary_version: str
    tags: list[TagVocabularyItem]


def tag_vocabulary_response() -> TagVocabularyResponse:
    """Project the in-process vocabulary onto the public wire model."""
    return TagVocabularyResponse(
        vocabulary_version=VOCABULARY_VERSION,
        tags=[
            TagVocabularyItem(
                id=entry.id,  # type: ignore[arg-type]
                name=entry.name,
                description=entry.description,
                aliases=list(entry.aliases),
                status=entry.status,
            )
            for entry in TAG_VOCABULARY
        ],
    )


def canonical_tag_id(value: str) -> str | None:
    """Return the stored identifier for an id, display name, or alias."""
    return _ALIAS_TO_ID.get(value.strip().casefold())


def search_terms_for_tags(tag_ids: list[str]) -> list[str]:
    """Names and aliases that full-text search must treat as the tagged object."""
    terms: list[str] = []
    seen: set[str] = set()
    for tag_id in tag_ids:
        entry = _BY_ID.get(tag_id)
        if entry is None:
            continue
        for term in (entry.name, *entry.aliases):
            folded = term.casefold()
            if folded in seen or folded == tag_id:
                continue
            seen.add(folded)
            terms.append(term)
    return terms


def publication_tag_errors(tags: list[str]) -> list[str]:
    """Field names for publication rejection of unknown or deprecated tags.

    Duplicate identifiers are rejected by the passport model. Local drafts are
    not constrained by membership; only publication is.
    """
    if len(tags) > MAX_TAGS:
        return ["tags"]
    invalid: list[str] = []
    for tag in tags:
        if len(tag) > MAX_TAG_LENGTH:
            invalid.append("tags")
            continue
        entry = _BY_ID.get(tag)
        if entry is None or entry.status != "active":
            invalid.append("tags")
    return sorted(set(invalid))


def nearest_tag_ids(value: str, *, limit: int = 3) -> list[str]:
    """Closest permitted identifiers for an unknown tag error."""
    return get_close_matches(value, TAG_IDS, n=limit, cutoff=0.4)


def is_tag_id_form(value: str) -> bool:
    """Vocabulary form only — membership is a separate check."""
    return 2 <= len(value) <= MAX_TAG_LENGTH and re.fullmatch(TAG_PATTERN, value) is not None
