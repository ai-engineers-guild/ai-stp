"""Deterministic index eligibility (SPEC-053 REQ-5313)."""

from __future__ import annotations

from ai_stp_contracts.seo import SeoIndexDecision, SeoIndexReason
from ai_stp_platform.seo.facts import PublicSubjectFacts


def decide_index(facts: PublicSubjectFacts) -> SeoIndexDecision:
    """Compute eligibility from lifecycle, visibility and kind-specific fullness."""
    reasons: list[SeoIndexReason] = []
    if facts.visibility != "public":
        reasons.append("not_public")
    if facts.lifecycle == "hidden":
        reasons.append("hidden")
    if facts.lifecycle == "blocked":
        reasons.append("blocked")
    if facts.lifecycle == "deprecated":
        reasons.append("deprecated")
    if facts.lifecycle == "unavailable":
        reasons.append("unavailable")
    primary = (facts.name or "").strip() and (facts.description or "").strip()
    if facts.kind != "country" and not primary:
        reasons.append("missing_primary_content")
    if facts.kind == "service":
        source = facts.extras.get("source_url")
        description = facts.extras.get("description") or facts.description
        if not isinstance(source, str) or not source.startswith("https://"):
            reasons.append("missing_source")
        if (
            not isinstance(description, str) or not description.strip()
        ) and "missing_primary_content" not in reasons:
            reasons.append("missing_primary_content")
    if facts.kind == "country":
        services = facts.extras.get("services")
        objects = facts.extras.get("objects")
        empty_services = not isinstance(services, list) or not services
        empty_objects = not isinstance(objects, list) or not objects
        if empty_services and empty_objects:
            reasons.append("empty_collection")
    if facts.kind == "article":
        body = facts.extras.get("body_digest")
        if not isinstance(body, str) or not body:
            reasons.append("missing_primary_content")
    unique = reasons == []
    if unique:
        return SeoIndexDecision(eligible=True, reasons=["eligible"])
    return SeoIndexDecision(eligible=False, reasons=reasons)
