"""Deterministic SEO projection (SPEC-053)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_stp_contracts.seo import (
    SEO_OG_HEIGHT,
    SEO_OG_WIDTH,
    SEO_SITEMAP_SHARD_LIMIT,
    SeoEnrichmentOutput,
    SeoProfileDocument,
    SeoSitemapUrl,
)
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.seo.builder import build_base_profile, profile_digest
from ai_stp_platform.seo.enrich import (
    SYSTEM_INSTRUCTION,
    SeoEnrichmentRejected,
    merge_enrichment,
    request_body,
    validate_enrichment_output,
)
from ai_stp_platform.seo.facts import (
    PublicSubjectFacts,
    SeoFactsInvalid,
    as_object_list,
    as_object_map,
    snapshot_payload,
)
from ai_stp_platform.seo.index_decision import decide_index
from ai_stp_platform.seo.metrics import record_seo_build, reset_seo_metrics, seo_metrics_snapshot
from ai_stp_platform.seo.og import png_dimensions, render_og_png
from ai_stp_platform.seo.sitemap import split_urls
from ai_stp_platform.seo.urls import canonical_url
from ai_stp_worker.handlers import REGISTRY

pytestmark = pytest.mark.platform

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _facts(**overrides: object) -> PublicSubjectFacts:
    values: dict[str, object] = {
        "kind": "component",
        "subject_id": "component_01jqzk7b8n4m6p2r9t5v0x3y70",
        "source_revision": "revision_" + "d" * 64,
        "locale": "en",
        "name": "Demo skill",
        "description": "Public skill for catalog search and install.",
        "summary": "Public skill for catalog search and install.",
        "lifecycle": "active",
        "visibility": "public",
        "published_at": NOW,
        "modified_at": NOW,
        "tags": ("skill",),
        "extras": {
            "purpose": "Public skill for catalog search and install.",
            "author_name": "Ada",
            "source_repository": "https://github.com/example/demo",
            "author_verified": True,
            "component_verified": True,
            "supported_os": ["linux"],
        },
    }
    values.update(overrides)
    return PublicSubjectFacts(**values)  # type: ignore[arg-type]


def _profile(facts: PublicSubjectFacts | None = None) -> SeoProfileDocument:
    subject = facts or _facts()
    return build_base_profile(
        subject,
        origin="https://example.test",
        revision_id="revision_" + "a" * 64,
        source_digest="sha256:" + "e" * 64,
    )


def test_job_registry_includes_seo_types() -> None:
    assert JobType.SEO_BUILD.value == "seo_build"
    assert JobType.SEO_ENRICH.value == "seo_enrich"
    assert JobType.SEO_BUILD in REGISTRY
    assert JobType.SEO_ENRICH in REGISTRY


def test_snapshot_rejects_secret_and_artifact_body() -> None:
    with pytest.raises(SeoFactsInvalid):
        snapshot_payload(_facts(extras={"api_key": "secret-value"}))
    with pytest.raises(SeoFactsInvalid):
        snapshot_payload(_facts(extras={"artifact_body": "zip-bytes"}))


@pytest.mark.parametrize("kind", ["component", "setup", "article", "service", "country"])
@pytest.mark.parametrize("locale", ["en", "ru"])
def test_base_profile_is_complete_without_network(kind: str, locale: str) -> None:
    extras: dict[str, object] = {
        "purpose": "Public subject",
        "author_name": "Ada" if kind != "country" else "",
        "article_type": "article",
        "body_digest": "sha256:" + "1" * 64,
        "body_excerpt": "Article body excerpt for indexing.",
        "source_url": "https://example.test/source",
        "description": "Service description for indexing.",
        "objects": [{"object_kind": "component", "stable_id": "c1", "name": "C"}],
        "services": [{"canonical_domain": "kaspi.kz", "name": "Kaspi"}],
        "source_repository": "https://github.com/example/demo",
    }
    facts = _facts(
        kind=kind,
        locale=locale,
        subject_id="KZ" if kind == "country" else "subject-1",
        extras=extras,
    )
    profile = _profile(facts)
    assert profile.title
    assert profile.description
    assert profile.heading
    assert profile.canonical_url.startswith("https://example.test/")
    assert profile.robots in {"index,follow", "noindex,follow"}
    assert profile.json_ld["@context"] == "https://schema.org"
    assert profile.social.image_url.endswith(".png")
    assert profile.generator.kind == "template"
    serialized = profile.model_dump(mode="json")
    assert "faq" not in str(serialized).lower()
    assert "aggregateRating" not in str(serialized)
    assert "offers" not in str(serialized)


def test_canonical_is_the_stable_subject_page() -> None:
    url = canonical_url("https://example.test", "component", "cid", "en")
    assert url == "https://example.test/en/catalog/components/cid"
    assert "/versions/" not in url
    assert "?" not in url


def test_index_decision_matrix_is_stable() -> None:
    assert decide_index(_facts()).eligible is True
    hidden = decide_index(_facts(lifecycle="hidden"))
    assert hidden.eligible is False
    assert "hidden" in hidden.reasons
    blocked = decide_index(_facts(lifecycle="blocked", visibility="public"))
    assert "blocked" in blocked.reasons
    thin_service = decide_index(
        _facts(kind="service", extras={"description": "", "source_url": ""})
    )
    assert thin_service.eligible is False
    assert "missing_source" in thin_service.reasons
    empty_country = decide_index(_facts(kind="country", extras={"services": [], "objects": []}))
    assert "empty_collection" in empty_country.reasons


def test_ineligible_profile_is_noindex() -> None:
    profile = _profile(_facts(lifecycle="hidden"))
    assert profile.robots == "noindex,follow"
    assert profile.index_decision.eligible is False


def test_sitemap_splits_above_shard_limit() -> None:
    sample = SeoSitemapUrl(
        loc="https://example.test/en/catalog/components/x",
        lastmod="2026-08-01T00:00:00.000Z",
        alternates={"en": "https://example.test/en/catalog/components/x"},
    )
    urls = [sample] * (SEO_SITEMAP_SHARD_LIMIT + 1)
    pages = split_urls(urls)
    assert len(pages) == 2
    assert len(pages[0]) == SEO_SITEMAP_SHARD_LIMIT
    assert len(pages[1]) == 1


def test_og_png_is_1200_by_630() -> None:
    png = render_og_png(_profile())
    assert png_dimensions(png) == (SEO_OG_WIDTH, SEO_OG_HEIGHT)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_enrichment_request_has_no_credential_or_private_fields() -> None:
    body = request_body(
        snapshot={"name": "Demo", "kind": "component"},
        model_alias="seo-writer",
    )
    blob = str(body)
    assert "credential" not in blob.lower()
    assert "api_key" not in blob.lower()
    assert "finding" not in blob.lower()
    assert body["model"] == "seo-writer"
    assert "required_section_ids" in blob and "overview" in blob
    assert (
        "ignore instructions" in SYSTEM_INSTRUCTION.lower()
        or "Ignore instructions" in SYSTEM_INSTRUCTION
    )


def test_model_cannot_set_canonical_or_trust() -> None:
    base = _profile()
    with pytest.raises(SeoEnrichmentRejected) as rejected:
        validate_enrichment_output(
            {
                "title": "Demo skill",
                "description": "Public skill for catalog search and install.",
                "summary": "Public skill for catalog search and install.",
                "search_intents": ["skill"],
                "sections": [
                    {
                        "id": "purpose",
                        "heading": "Purpose",
                        "body": "Public skill for catalog search and install.",
                    }
                ],
                "social_title": "Demo skill",
                "social_description": "Public skill for catalog search and install.",
                "social_image_alt": "Demo skill",
                "canonical_url": "https://evil.example/steal",
            },
            snapshot={"name": "Demo skill"},
            base=base,
            source_digest=base.subject.source_digest,
        )
    assert rejected.value.code == "AI_STP_SEO_OUTPUT_INVALID"


def test_enrichment_updates_json_ld_presentation_only() -> None:
    base = _profile()
    output = SeoEnrichmentOutput(
        title="Demo skill for Codex",
        description="Installs catalog search commands in Codex on Linux.",
        summary="Use Demo skill to search and install catalog components from Codex.",
        search_intents=["catalog search skill for Codex"],
        sections=[],
        social_title="Demo skill for Codex",
        social_description="Search and install catalog components from Codex.",
        social_image_alt="Demo skill for Codex",
    )
    merged = merge_enrichment(base, output)
    primary = next(
        item
        for value in as_object_list(merged.json_ld["@graph"])
        if (item := as_object_map(value)) is not None
        and item["@type"] not in {"BreadcrumbList", "Person", "Organization"}
    )
    base_primary = next(
        item
        for value in as_object_list(base.json_ld["@graph"])
        if (item := as_object_map(value)) is not None
        and item["@type"] not in {"BreadcrumbList", "Person", "Organization"}
    )
    assert primary["name"] == output.title
    assert primary["description"] == output.description
    assert primary["url"] == base_primary["url"]


@pytest.mark.parametrize(
    "raw",
    [
        "not-an-object",
        {
            "title": "Demo",
            "description": "Public skill for catalog search and install.",
            "summary": "<script>alert(1)</script>",
            "search_intents": [],
            "sections": [],
            "social_title": "Demo",
            "social_description": "Public skill for catalog search and install.",
            "social_image_alt": "Demo",
        },
        {
            "title": "Demo",
            "description": "Public skill for catalog search and install.",
            "summary": "Visit https://evil.example/phish now.",
            "search_intents": [],
            "sections": [],
            "social_title": "Demo",
            "social_description": "Public skill for catalog search and install.",
            "social_image_alt": "Demo",
        },
    ],
)
def test_enrichment_corpus_rejects_unsafe_output(raw: object) -> None:
    with pytest.raises(SeoEnrichmentRejected):
        validate_enrichment_output(
            raw,
            snapshot={"name": "Demo skill"},
            base=_profile(),
            source_digest="sha256:" + "e" * 64,
        )


def test_stale_digest_is_rejected() -> None:
    with pytest.raises(SeoEnrichmentRejected) as rejected:
        validate_enrichment_output(
            {
                "title": "Demo skill",
                "description": "Public skill for catalog search and install.",
                "summary": "Public skill for catalog search and install.",
                "search_intents": ["skill"],
                "sections": [
                    {
                        "id": "purpose",
                        "heading": "Purpose",
                        "body": "Public skill for catalog search and install.",
                    }
                ],
                "social_title": "Demo skill",
                "social_description": "Public skill for catalog search and install.",
                "social_image_alt": "Demo skill",
            },
            snapshot={"name": "Demo skill"},
            base=_profile(),
            source_digest="sha256:" + "0" * 64,
        )
    assert rejected.value.code == "AI_STP_SEO_SOURCE_STALE"


def test_metrics_omit_prompt_body_and_subject_id() -> None:
    reset_seo_metrics()
    record_seo_build(outcome="base_active", duration_ms=12, index_reasons=["eligible"])
    snap = seo_metrics_snapshot()
    blob = str(snap)
    assert "prompt" not in blob
    assert "component_01" not in blob
    assert snap["seo_build_total"] == 1
    assert snap["seo_active_base_total"] == 1


def test_json_ld_matches_visible_title() -> None:
    profile = _profile()
    graph = as_object_list(profile.json_ld.get("@graph"))
    primary: dict[str, object] | None = None
    for node in graph:
        mapped = as_object_map(node)
        if mapped is not None and mapped.get("@type") == "SoftwareSourceCode":
            primary = mapped
            break
    assert primary is not None
    assert primary["name"] == profile.title
    assert primary["description"] == profile.description


def test_closed_enrichment_schema_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SeoEnrichmentOutput.model_validate(
            {
                "title": "Demo skill",
                "description": "Public skill for catalog search and install.",
                "summary": "Public skill for catalog search and install.",
                "search_intents": [],
                "sections": [],
                "social_title": "Demo skill",
                "social_description": "Public skill for catalog search and install.",
                "social_image_alt": "Demo skill",
                "trust_lane": "authoritative",
            }
        )


def test_profile_digest_is_stable() -> None:
    first = profile_digest(_profile())
    second = profile_digest(_profile())
    assert first == second
    assert first.startswith("sha256:")


def test_hreflang_only_includes_existing_locales() -> None:
    profile = build_base_profile(
        _facts(),
        origin="https://example.test",
        revision_id="revision_" + "a" * 64,
        source_digest="sha256:" + "e" * 64,
        existing_locales={"en": "https://example.test/en/catalog/components/x"},
    )
    assert set(profile.alternates) == {"en"}
    ru = build_base_profile(
        _facts(locale="ru"),
        origin="https://example.test",
        revision_id="revision_" + "a" * 64,
        source_digest="sha256:" + "e" * 64,
        existing_locales={"en": "https://example.test/en/catalog/components/x"},
    )
    assert set(ru.alternates) == {"en", "ru"}


def test_component_profile_has_required_visible_sections() -> None:
    ids = {section.id for section in _profile().sections}
    assert {"purpose", "verification", "source", "author"} <= ids
    for section in _profile().sections:
        assert section.body
        assert section.provenance == "template"


def test_internal_links_are_absolute_canonical_hrefs() -> None:
    profile = _profile(
        _facts(
            extras={
                "purpose": "Public skill",
                "services": [{"canonical_domain": "kaspi.kz", "name": "Kaspi"}],
            }
        )
    )
    assert profile.internal_links
    for link in profile.internal_links:
        assert link.href.startswith("https://example.test/")
        assert "?" not in link.href
        assert "/versions/" not in link.href


def test_job_payload_omits_secrets() -> None:
    from ai_stp_platform.seo.enqueue import job_payload_is_safe

    assert job_payload_is_safe(
        {
            "subject_kind": "article",
            "subject_id": "article:immutable-artifacts",
            "locale": "en",
            "source_digest": "sha256:" + "1" * 64,
            "template_version": "v1",
            "prompt_version": "v1",
        }
    )
    assert not job_payload_is_safe({"credential": "secret-value"})
    assert not job_payload_is_safe({"token": "leak"})


def test_duplicate_summary_is_rejected() -> None:
    base = _profile()
    payload = {
        "title": "Demo skill",
        "description": "Public skill for catalog search and install.",
        "summary": "Public skill for catalog search and install.",
        "search_intents": ["skill"],
        "sections": [
            {
                "id": "purpose",
                "heading": "Purpose",
                "body": "Public skill for catalog search and install.",
            }
        ],
        "social_title": "Demo skill",
        "social_description": "Public skill for catalog search and install.",
        "social_image_alt": "Demo skill",
    }
    with pytest.raises(SeoEnrichmentRejected) as rejected:
        validate_enrichment_output(
            payload,
            snapshot={"name": "Demo skill"},
            base=base,
            source_digest=base.subject.source_digest,
            duplicate_summaries=["Public skill for catalog search and install."],
        )
    assert rejected.value.code == "AI_STP_SEO_OUTPUT_INVALID"


def _quality_candidate(kind: str) -> tuple[dict[str, object], dict[str, object]]:
    sections: list[dict[str, str]] = []
    extras: dict[str, object] = {}
    if kind == "component":
        extras = {
            "provides_capabilities": ["workflow orchestration"],
            "runtime_requirements": ["herdr"],
            "permission_groups": {"process": ["herdr"]},
        }
        sections = [
            {
                "id": "overview",
                "heading": "Coordinate coding agents from Codex",
                "body": (
                    "Start a Herdr run and assign project-aware roles to the participating agents."
                ),
            },
            {
                "id": "capabilities",
                "heading": "Track execution and review results",
                "body": "Follow workflow state, apply execution guards, and retain review results.",
            },
            {
                "id": "requirements",
                "heading": "Herdr runtime and process access",
                "body": (
                    "The skill requires the herdr runtime and permission to launch "
                    "the herdr process."
                ),
            },
        ]
    elif kind == "service":
        extras = {
            "description": "A documented payment service used by teams in Kazakhstan.",
            "source_url": "https://kaspi.example/about",
            "objects": [{"name": "Payment helper"}],
            "countries": ["KZ"],
        }
        sections = [
            {
                "id": "overview",
                "heading": "Use Kaspi integrations from the catalog",
                "body": (
                    "Find catalog components that connect coding workflows with the Kaspi service."
                ),
            },
            {
                "id": "related-components",
                "heading": "Components linked to Kaspi",
                "body": "The catalog currently links the Payment helper component to this service.",
            },
            {
                "id": "coverage",
                "heading": "Service availability by country",
                "body": "The published service relationship covers KZ.",
            },
        ]
    return (
        {
            "kind": kind,
            "name": "Workflow Herdr" if kind != "service" else "Kaspi",
            "description": (
                "Starts bounded Herdr work runs with roles, topology, state transitions, "
                "guards, and review receipts."
                if kind != "service"
                else "A documented payment service used by teams in Kazakhstan."
            ),
            "extras": extras,
        },
        {
            "title": (
                "Workflow Herdr multi-agent runs for Codex"
                if kind != "service"
                else "Kaspi automation components for coding agents"
            ),
            "description": (
                "Run coordinated coding tasks across multiple agents in Herdr from Codex, with "
                "assigned roles, execution guards, workflow tracking, and review results."
                if kind != "service"
                else "Find Kaspi automation components published in the catalog, see their "
                "published country coverage, and open each catalog relationship page."
            ),
            "summary": (
                "Workflow Herdr starts coordinated agent tasks from Codex. It assigns roles and "
                "records execution state so developers can inspect the resulting review."
                if kind != "service"
                else "Kaspi is linked to published automation components in the catalog. The "
                "service page shows available integrations and their country coverage."
            ),
            "search_intents": (
                [
                    "Herdr coding agent workflow",
                    "Codex multi agent orchestration",
                    "Herdr review runs",
                ]
                if kind != "service"
                else [
                    "Kaspi automation components",
                    "Kaspi coding agent integration",
                    "Kaspi KZ tools",
                ]
            ),
            "sections": sections,
            "social_title": "Workflow Herdr for Codex"
            if kind != "service"
            else "Kaspi automations",
            "social_description": "Inspect the published capabilities, requirements, and coverage.",
            "social_image_alt": "Catalog diagram for the published integration",
        },
    )


@pytest.mark.parametrize("kind", ["component", "service"])
def test_quality_gate_accepts_specific_kind_coverage(kind: str) -> None:
    snapshot, payload = _quality_candidate(kind)
    parsed = validate_enrichment_output(
        payload,
        snapshot=snapshot,
        base=_profile(),
        source_digest=_profile().subject.source_digest,
    )
    assert parsed.sections


def test_quality_gate_rejects_invented_service_hosting_claim() -> None:
    snapshot, payload = _quality_candidate("service")
    payload["summary"] = (
        "Kaspi hosts the linked component for developers. The catalog lists its country coverage."
    )
    with pytest.raises(SeoEnrichmentRejected, match="unsupported service claim"):
        validate_enrichment_output(
            payload,
            snapshot=snapshot,
            base=_profile(),
            source_digest=_profile().subject.source_digest,
        )


def test_quality_gate_rejects_service_without_authoritative_description() -> None:
    snapshot, payload = _quality_candidate("service")
    snapshot["extras"] = {"objects": [{"name": "Payment helper"}], "countries": ["KZ"]}
    with pytest.raises(SeoEnrichmentRejected, match="lacks authoritative description"):
        validate_enrichment_output(
            payload,
            snapshot=snapshot,
            base=_profile(),
            source_digest=_profile().subject.source_digest,
        )


def test_quality_gate_rejects_copied_machine_description() -> None:
    snapshot, payload = _quality_candidate("component")
    payload["description"] = snapshot["description"]
    with pytest.raises(SeoEnrichmentRejected, match="source description copied"):
        validate_enrichment_output(
            payload,
            snapshot=snapshot,
            base=_profile(),
            source_digest=_profile().subject.source_digest,
        )


def test_quality_gate_matches_subject_name_across_slug_punctuation() -> None:
    snapshot, payload = _quality_candidate("component")
    snapshot["name"] = "Workflow-Herdr"
    parsed = validate_enrichment_output(
        payload,
        snapshot=snapshot,
        base=_profile(),
        source_digest=_profile().subject.source_digest,
    )
    assert parsed.title == payload["title"]


def test_quality_gate_requires_agent_outcome_for_orchestration_component() -> None:
    snapshot, payload = _quality_candidate("component")
    payload["title"] = "Workflow Herdr task coordination for Codex"
    payload["description"] = (
        "Use Workflow Herdr in Codex to divide development tasks by role, coordinate parallel "
        "work, and collect independent review results."
    )
    payload["summary"] = (
        "Workflow Herdr coordinates multiple coding agents in Codex. It records execution and "
        "review results for each assigned role."
    )
    with pytest.raises(SeoEnrichmentRejected, match="agent outcome missing"):
        validate_enrichment_output(
            payload,
            snapshot=snapshot,
            base=_profile(),
            source_digest=_profile().subject.source_digest,
        )


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        ("short_title", "title length"),
        ("long_title", "title length"),
        ("thin_description", "description length"),
        ("long_description", "description length"),
        ("thin_intents", "search intent count"),
        ("generic_heading", "generic section heading"),
        ("missing_section", "section coverage"),
    ],
)
def test_quality_gate_rejects_thin_or_generic_model_output(
    mutation: str, expected_message: str
) -> None:
    snapshot, payload = _quality_candidate("component")
    if mutation == "short_title":
        payload["title"] = "Workflow Herdr"
    elif mutation == "long_title":
        payload["title"] = "Workflow Herdr " + "x" * 46
    elif mutation == "thin_description":
        payload["description"] = "A powerful and seamless workflow for everyone."
    elif mutation == "long_description":
        payload["description"] = str(payload["description"]) + " Extra detail for search."
    elif mutation == "thin_intents":
        payload["search_intents"] = ["Herdr"]
    elif mutation == "generic_heading":
        sections = payload["sections"]
        assert isinstance(sections, list) and isinstance(sections[0], dict)
        sections[0]["heading"] = "Overview"
    else:
        sections = payload["sections"]
        assert isinstance(sections, list)
        payload["sections"] = sections[:-1]
    with pytest.raises(SeoEnrichmentRejected, match=expected_message):
        validate_enrichment_output(
            payload,
            snapshot=snapshot,
            base=_profile(),
            source_digest=_profile().subject.source_digest,
        )


def test_article_enrichment_cannot_replace_published_sections() -> None:
    snapshot, payload = _quality_candidate("component")
    snapshot.update(kind="article", name="Workflow Herdr")
    with pytest.raises(SeoEnrichmentRejected, match="section coverage"):
        validate_enrichment_output(
            payload,
            snapshot=snapshot,
            base=_profile(),
            source_digest=_profile().subject.source_digest,
        )
