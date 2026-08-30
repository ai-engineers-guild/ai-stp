"""Allowlist fact collection and snapshot digest (SPEC-053 REQ-5304)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from ai_stp_contracts.seo import (
    ARTICLE_BODY_DOMAIN,
    FORBIDDEN_FACT_KEYS,
    SEO_SNAPSHOT_DOMAIN,
    SEO_SUBJECT_KINDS,
    SeoLocale,
    SeoSubjectKind,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.timestamps import format_timestamp

type Locale = Literal["ru", "en"]


class SeoFactsInvalid(ValueError):
    """Snapshot facts failed the public allowlist."""

    def __init__(self, message: str = "SEO facts invalid") -> None:
        super().__init__(message)
        self.code = "AI_STP_SEO_FACTS_INVALID"


@dataclass(frozen=True)
class PublicSubjectFacts:
    """Pure public aggregate used by the deterministic builder."""

    kind: SeoSubjectKind
    subject_id: str
    source_revision: str
    locale: Locale
    name: str
    description: str
    summary: str
    lifecycle: str
    visibility: str
    published_at: datetime
    modified_at: datetime
    tags: tuple[str, ...]
    extras: Mapping[str, object]


def _reject_forbidden(node: object, *, path: str = "") -> None:
    if isinstance(node, dict):
        mapping = cast(dict[str, object], node)
        for key, value in mapping.items():
            lowered = key.lower()
            if lowered in FORBIDDEN_FACT_KEYS or "secret" in lowered or "password" in lowered:
                raise SeoFactsInvalid(f"forbidden fact key: {path}{key}")
            if lowered.endswith("_body") and key not in {"body_excerpt"}:
                raise SeoFactsInvalid(f"forbidden fact key: {path}{key}")
            _reject_forbidden(value, path=f"{path}{key}.")
        return
    if isinstance(node, list):
        for index, item in enumerate(cast(list[object], node)):
            _reject_forbidden(item, path=f"{path}{index}.")


def snapshot_payload(facts: PublicSubjectFacts) -> dict[str, object]:
    """Canonical public aggregate. Secrets and artifact bodies never enter."""
    payload: dict[str, object] = {
        "kind": facts.kind,
        "subject_id": facts.subject_id,
        "source_revision": facts.source_revision,
        "locale": facts.locale,
        "name": facts.name,
        "description": facts.description,
        "summary": facts.summary,
        "lifecycle": facts.lifecycle,
        "visibility": facts.visibility,
        "published_at": format_timestamp(facts.published_at),
        "modified_at": format_timestamp(facts.modified_at),
        "tags": list(facts.tags),
        "extras": dict(facts.extras),
    }
    _reject_forbidden(payload)
    if not facts.name.strip() and facts.kind != "country":
        raise SeoFactsInvalid("primary name missing")
    return payload


def snapshot_digest(facts: PublicSubjectFacts) -> str:
    """Digest of the whole public aggregate, not of a subset of fields."""
    return digest_canonical(SEO_SNAPSHOT_DOMAIN, cast(JsonValue, snapshot_payload(facts)))


def article_body_digest(body: str) -> str:
    return digest_bytes(ARTICLE_BODY_DOMAIN, body.encode("utf-8"))


def collect_public_facts(facts: PublicSubjectFacts) -> dict[str, object]:
    """Return the stored snapshot document after allowlist validation."""
    payload = snapshot_payload(facts)
    payload["source_digest"] = snapshot_digest(facts)
    return payload


def extras_text(extras: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = extras.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def as_object_map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def as_object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return list(cast(list[object], value))


def as_str_list(value: object) -> list[str]:
    return [item for item in as_object_list(value) if isinstance(item, str)]


def extras_list(extras: Mapping[str, object], key: str) -> list[object]:
    return as_object_list(extras.get(key))


def mapping_text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    return str(value) if value is not None else ""


def parse_subject_kind(value: object) -> SeoSubjectKind:
    if isinstance(value, str) and value in SEO_SUBJECT_KINDS:
        return value
    raise ValueError("unknown SEO subject kind")


def parse_locale(value: object) -> SeoLocale:
    if value == "ru":
        return "ru"
    if value == "en":
        return "en"
    raise ValueError("unknown SEO locale")
